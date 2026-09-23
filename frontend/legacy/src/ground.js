import * as THREE from 'three'
import { scene } from './scene.js'
import { SCENE_CONFIG } from './config.js'

// ===================== 地面 =====================

const groundGeo = new THREE.PlaneGeometry(120, 120)   // 平面几何体
const groundMat = new THREE.MeshStandardMaterial({ 
  color: 0xe6f7f5, 
  roughness: 0.9
})
export const ground = new THREE.Mesh(groundGeo, groundMat)
ground.rotation.x = -Math.PI / 2   // 旋转至水平
// 地面比墙体底部低一点点，墙体不会穿插、悬浮
ground.position.y = -0.1
ground.receiveShadow = true   // 接收阴影
scene.add(ground)

// 网格辅助线
export const gridHelper = new THREE.GridHelper(120, 24, 0x21aba5, 0xa8e6e0)
// (总尺寸, 细分数, 中心轴线颜色, 普通网格线颜色)
gridHelper.position.y = ground.position.y + 0.01   // 解决 Z-fighting（面闪烁）
scene.add(gridHelper)