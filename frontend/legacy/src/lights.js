import * as THREE from 'three'
import { scene } from './scene.js'

// ===================== 光源 =====================

// 主平行光：模拟太阳光，有方向、能产生阴影，塑造明暗立体感
export const dirLight = new THREE.DirectionalLight(0xffffff, 1.0)
dirLight.position.set(-5, 8, -8)
dirLight.castShadow = true             // 开启投影阴影
dirLight.shadow.mapSize.set(2048, 2048)   // 阴影贴图分辨率
dirLight.shadow.bias = -0.0005         // 阴影偏移，解决痤疮伪影

// 新增：扩大阴影相机范围
dirLight.shadow.camera.left = -60
dirLight.shadow.camera.right = 60
dirLight.shadow.camera.top = 60
dirLight.shadow.camera.bottom = -60
dirLight.shadow.camera.near = 0.1
dirLight.shadow.camera.far = 200

scene.add(dirLight)

// 环境光：全局漫反射，防止物体背光面全黑
export const ambientLight = new THREE.AmbientLight(0xffffff, 1)
scene.add(ambientLight)

// 补光：弱平行光，柔化阴影死黑区域，画面更柔和
export const fillLight = new THREE.DirectionalLight(0xffffff, 0.3)
fillLight.position.set(-3, 4, -3)
scene.add(fillLight)