import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

const UP = new THREE.Vector3(0, 1, 0)
const _dir = new THREE.Vector3()
const _normal = new THREE.Vector3()
const _center = new THREE.Vector3()

function jsonToThree(arr) {
  return new THREE.Vector3(arr[0], arr[2], arr[1])
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

function buildWalls(group, geo, layers) {
  ;(geo.walls || []).forEach(wall => {
    const start = jsonToThree(wall.start)
    const end = jsonToThree(wall.end)
    const length = start.distanceTo(end)
    _dir.subVectors(end, start).normalize()
    _normal.crossVectors(UP, _dir).normalize()
    _center.addVectors(start, end).multiplyScalar(0.5)
    _center.y = wall.height_m / 2

    const total = layers.reduce((s, l) => s + l.thickness, 0)
    let z = -total / 2
    ;(layers || []).forEach(layer => {
      if (layer.thickness <= 0) return
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(length, wall.height_m, layer.thickness),
        makeLayerMaterial(layer)
      )
      mesh.position.copy(_center).addScaledVector(_normal, z + layer.thickness / 2)
      const zAxis = _normal.clone().negate()
      mesh.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(_dir, UP, zAxis))
      group.add(mesh)
      z += layer.thickness
    })
  })
}

function buildOpenings(group, geo, layers) {
  const total = layers.reduce((s, l) => s + l.thickness, 0)
  ;(geo.openings || []).forEach(opening => {
    const wall = (geo.walls || []).find(w => w.wall_id === opening.host_wall)
    if (!wall) return
    const start = jsonToThree(wall.start)
    const end = jsonToThree(wall.end)
    _dir.subVectors(end, start).normalize()
    _normal.crossVectors(UP, _dir).normalize()

    const halfW = opening.width_m / 2
    const panelCenter = start.clone().addScaledVector(_dir, opening.position_along_wall_m + halfW)
    panelCenter.y = opening.sill_height_m + opening.height_m / 2
    panelCenter.addScaledVector(_normal, total / 2 + 0.02)

    const isWindow = opening.type === 'window'
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(opening.width_m + (isWindow ? 0.08 : 0), opening.height_m, 0.03),
      new THREE.MeshPhysicalMaterial({
        color: isWindow ? 0xbde8ff : 0x2f3e46,
        transparent: isWindow,
        opacity: isWindow ? 0.55 : 1,
        roughness: isWindow ? 0.12 : 0.6,
        metalness: isWindow ? 0.25 : 0.05,
        side: THREE.DoubleSide
      })
    )
    mesh.position.copy(panelCenter)
    const zAxis = _normal.clone().negate()
    mesh.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(_dir, UP, zAxis))
    group.add(mesh)
  })
}

// 首页方案卡片里的可旋转 3D 缩略模型（与详情页同一套建筑几何）
export function createSchemeThumbnail(container, layers, geo) {
  const w = container.clientWidth || 260
  const h = container.clientHeight || 150

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.domElement.style.width = '100%'
  renderer.domElement.style.height = '100%'
  container.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 500)

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableZoom = false
  controls.enablePan = false
  controls.autoRotate = true
  controls.autoRotateSpeed = 1.6
  controls.target.set(0, 0, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.9))
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.85)
  dirLight.position.set(4, 6, 3)
  scene.add(dirLight)

  const group = new THREE.Group()
  scene.add(group)

  if (geo?.walls?.length) {
    buildWalls(group, geo, layers)
    buildOpenings(group, geo, layers)
  } else {
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(4, 3.2, 2.6),
      new THREE.MeshStandardMaterial({ color: 0xf4f6f8, roughness: 0.7, metalness: 0.05 })
    )
    base.position.y = 1.6
    group.add(base)
    const insul = layers.find(l => l.is_insulation)
    if (insul) {
      const shell = new THREE.Mesh(
        new THREE.BoxGeometry(4.16, 3.36, 2.76),
        new THREE.MeshStandardMaterial({
          color: insul.color,
          transparent: true,
          opacity: 0.6,
          roughness: 0.5,
          metalness: 0.1
        })
      )
      shell.position.y = 1.6
      group.add(shell)
    }
  }

  // 建筑居中并自动适配相机
  const bbox = new THREE.Box3().setFromObject(group)
  const size = bbox.getSize(new THREE.Vector3())
  const center = bbox.getCenter(new THREE.Vector3())
  group.position.sub(center)
  const maxDim = Math.max(size.x, size.y, size.z) || 5

  const dist = maxDim * 1.5
  const defaultPos = new THREE.Vector3(-dist * 0.6, dist * 0.3, -dist * 0.7)
  camera.position.copy(defaultPos)
  camera.lookAt(0, 0, 0)
  controls.target.set(0, 0, 0)
  controls.update()

  let resizeObserver = null
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      const cw = container.clientWidth || 0
      const ch = container.clientHeight || 0
      if (!cw || !ch) return
      camera.aspect = cw / ch
      camera.updateProjectionMatrix()
      renderer.setSize(cw, ch)
    })
    resizeObserver.observe(container)
  }

  return {
    renderer,
    scene,
    camera,
    controls,
    update() {
      const cw = container.clientWidth || 0
      const chh = container.clientHeight || 0
      if (cw && chh) {
        const pr = window.devicePixelRatio || 1
        if (
          Math.abs(renderer.domElement.width - cw * pr) > 2 ||
          Math.abs(renderer.domElement.height - chh * pr) > 2
        ) {
          camera.aspect = cw / chh
          camera.updateProjectionMatrix()
          renderer.setSize(cw, chh)
        }
      }
      controls.update()
      renderer.render(scene, camera)
    },
    resize() {
      const w = container.clientWidth || 260
      const h = container.clientHeight || 150
      if (!w || !h) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
      renderer.render(scene, camera)
    },
    reset() {
      camera.position.copy(defaultPos)
      controls.target.set(0, 0, 0)
      controls.update()
      renderer.render(scene, camera)
    },
    dispose() {
      if (resizeObserver) resizeObserver.disconnect()
      controls.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement)
      }
    }
  }
}