import * as THREE from 'three'
import { scene, camera, controls } from './scene.js'
import { state } from './config.js'
import { resetEntrance } from './animation.js'
import officeGeo from '../../../fixtures/demo/frontend-data/geo/geometry_office_v2.json'
import dormGeo from '../../../fixtures/demo/frontend-data/geo/geometry_dorm_v2.json'
import teachingGeo from '../../../fixtures/demo/frontend-data/geo/geometry_teaching_v2.json'

// 建筑类型 -> 几何 JSON
export const BUILDING_GEO = {
  office: officeGeo,
  dorm: dormGeo,
  school: teachingGeo,
  teaching: teachingGeo
}

// ========== 坐标转换 ==========
// JSON 约定: Z 向上, 水平面是 X-Y
// Three.js: Y 向上, 水平面是 X-Z
// 转换: JSON(x, y, z) → Three.js(x, z, y)

function jsonToThree(arr) {
  return new THREE.Vector3(arr[0], arr[2], arr[1])
}

const _dir = new THREE.Vector3()
const _normal = new THREE.Vector3()
const _center = new THREE.Vector3()

// 删除上一栋建筑
export function clearBuilding() {
  state.buildingMeshes.forEach(mesh => {
    mesh.geometry?.dispose()
    if (Array.isArray(mesh.material)) {
      mesh.material.forEach(m => m.dispose())
    } else {
      mesh.material?.dispose()
    }
  })
  if (state.buildingGroup) {
    scene.remove(state.buildingGroup)
    state.buildingGroup = null
  }
  state.buildingMeshes = []
}

function makeLayerMaterial(layer) {
  const params = {
    color: layer.color,
    roughness: layer.roughness ?? 0.5,
    metalness: layer.metalness ?? 0.1,
    side: THREE.DoubleSide
  }
  if (layer.transparent) {
    params.transparent = true
    params.opacity = layer.opacity ?? 0.75
    params.depthWrite = false
  }
  if (layer.clearcoat !== undefined) params.clearcoat = layer.clearcoat
  return new THREE.MeshPhysicalMaterial(params)
}

// 创建一面墙（多层构造）
function createWall(wall, layers) {
  const start = jsonToThree(wall.start)
  const end = jsonToThree(wall.end)
  const length = start.distanceTo(end)

  // 墙走向（水平面 X-Z 内）
  _dir.subVectors(end, start).normalize()
  
  // 墙法线（水平面内，指向建筑外侧）
  // up × dir = normal（右手系，确保朝外）
  const up = new THREE.Vector3(0, 1, 0)
  _normal.crossVectors(up, _dir).normalize()
  
  _center.addVectors(start, end).multiplyScalar(0.5)
  _center.y = wall.height_m / 2

  const totalThickness = layers.reduce((s, l) => s + l.thickness, 0)
  let currentOffset = -totalThickness / 2

  layers.forEach(layer => {
    if (layer.thickness <= 0) return

    // 修复 Z-fighting：层间留 0.0005m 间隙
    const gap = 0.0005
    const actualThickness = Math.max(0.001, layer.thickness - gap * 2)

    // BoxGeometry: width=长度(X), height=墙高(Y), depth=厚度(Z)
    const geometry = new THREE.BoxGeometry(length, wall.height_m, actualThickness)
    const mesh = new THREE.Mesh(geometry, makeLayerMaterial(layer))
    
    // 位置：沿法线方向偏移
    const offset = currentOffset + layer.thickness / 2
    mesh.position.copy(_center).addScaledVector(_normal, offset)
    
    // 旋转：Box X→dir, Y→up, Z→-normal（因为 dir×up = -normal）
    const zAxis = _normal.clone().negate()
    const basis = new THREE.Matrix4().makeBasis(_dir, up, zAxis)
    mesh.quaternion.setFromRotationMatrix(basis)
    
    mesh.castShadow = true
    mesh.receiveShadow = false
    mesh.userData = {
      type: 'wall',
      wallId: wall.wall_id,
      orientation: wall.orientation,
      layerName: layer.name,
      layer: { ...layer }
    }
    
    state.buildingGroup.add(mesh)
    state.buildingMeshes.push(mesh)
    currentOffset += layer.thickness
  })

  return totalThickness
}

// 创建窗户/门
function createOpening(opening, totalThickness) {
  const wall = state.currentGeo?.walls.find(w => w.wall_id === opening.host_wall)
  if (!wall) return

  const start = jsonToThree(wall.start)
  const end = jsonToThree(wall.end)
  
  _dir.subVectors(end, start).normalize()
  const up = new THREE.Vector3(0, 1, 0)
  _normal.crossVectors(up, _dir).normalize()

  const halfW = opening.width_m / 2
  const panelCenter = start.clone().addScaledVector(_dir, opening.position_along_wall_m + halfW)
  panelCenter.y = opening.sill_height_m + opening.height_m / 2
  panelCenter.addScaledVector(_normal, totalThickness / 2 + 0.02)

  const isWindow = opening.type === 'window'
  const material = new THREE.MeshPhysicalMaterial({
    color: isWindow ? 0xbde8ff : 0x2f3e46,
    transparent: isWindow,
    opacity: isWindow ? 0.55 : 1,
    roughness: isWindow ? 0.12 : 0.6,
    metalness: isWindow ? 0.25 : 0.05,
    side: THREE.DoubleSide
  })
  
  const geometry = new THREE.BoxGeometry(
    opening.width_m + (isWindow ? 0.08 : 0),
    opening.height_m,
    0.03
  )
  
  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.copy(panelCenter)
  
  // 同样的旋转
  const zAxis = _normal.clone().negate()
  const basis = new THREE.Matrix4().makeBasis(_dir, up, zAxis)
  mesh.quaternion.setFromRotationMatrix(basis)
  
  mesh.castShadow = true
  mesh.userData = {
    type: opening.type,
    openingId: opening.opening_id,
    wallId: wall.wall_id
  }
  
  state.buildingGroup.add(mesh)
  state.buildingMeshes.push(mesh)
}

// 用当前 state.layers 重建整栋建筑
export function buildBuilding(geo, options = {}) {
  clearBuilding()
  state.currentGeo = geo
  state.currentBuildingId = geo.building_id

  state.buildingGroup = new THREE.Group()
  scene.add(state.buildingGroup)

  const layers = state.layers
  let maxThickness = 0
  
  ;(geo.walls || []).forEach(wall => {
    const t = createWall(wall, layers)
    maxThickness = Math.max(maxThickness, t)
  })
  
  ;(geo.openings || []).forEach(opening => createOpening(opening, maxThickness))

  // ========== 新增：将建筑中心对齐到原点 ==========
  const bbox = new THREE.Box3()
  state.buildingMeshes.forEach(mesh => {
    const meshBbox = new THREE.Box3().setFromObject(mesh)
    bbox.union(meshBbox)
  })
  const center = new THREE.Vector3()
  bbox.getCenter(center)
  // 只在水平面（X-Z）上居中，Y 轴保持原高度不变
  state.buildingGroup.position.set(-center.x, 0, -center.z)
  // ================================================

  // 只在初始加载时调整相机，重建时不调整
  if (options.fitCamera !== false) {
    fitBuildingCamera(geo)
  }
  
  resetEntrance()
}

export function rebuildBuilding() {
  if (!state.currentGeo) return
  
  // 记录各层当前的显示状态
  const visibilityState = {}
  state.buildingMeshes.forEach(mesh => {
    const layerName = mesh.userData.layerName
    if (layerName && visibilityState[layerName] === undefined) {
      visibilityState[layerName] = mesh.visible
    }
  })
  
  // 重建，不调整相机
  buildBuilding(state.currentGeo, { fitCamera: false })
  
  // 恢复各层的显示状态
  state.buildingMeshes.forEach(mesh => {
    const layerName = mesh.userData.layerName
    if (layerName && visibilityState[layerName] !== undefined) {
      mesh.visible = visibilityState[layerName]
    }
  })
}

// 把相机对准建筑
export function fitBuildingCamera(geo) {
  // 优先用几何包围盒算尺寸，后端动态 JSON 不一定带 footprint/floors
  const box = new THREE.Box3()
  ;(geo.walls || []).forEach(wall => {
    const start = jsonToThree(wall.start)
    const end = jsonToThree(wall.end)
    const h = wall.height_m || 0
    box.expandByPoint(start)
    box.expandByPoint(end)
    box.expandByPoint(new THREE.Vector3(start.x, h, start.z))
    box.expandByPoint(new THREE.Vector3(end.x, h, end.z))
  })
  const size = box.getSize(new THREE.Vector3())
  const length = geo.footprint?.length_m || size.x || 50
  const width = geo.footprint?.width_m || size.z || 20
  const height = (geo.floors ?? 1) * (geo.floor_height_m ?? 3.6) || size.y || 18
  
  const target = new THREE.Vector3(0,0,0)
  const dist = Math.max(length, width, height) * 1.5

  controls.minDistance = dist * 0.3
  controls.maxDistance = dist * 5

  camera.position.set(
    target.x - dist * 0.6,   // ← 西北：X 负方向（左后方）
    target.y + dist * 0.3,   // ↑ 俯视角度
    target.z - dist * 0.7    // ← 西北：Z 负方向（左后方）
  )
  
  controls.target.copy(target)
  controls.update()
}
