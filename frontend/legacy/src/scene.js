import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { SCENE_CONFIG } from './config.js'

// ===================== 场景、相机、渲染器、控制器 =====================

// 透视相机（垂直视野角度,画布宽高比,近裁剪面,远裁剪面）
// 坐标 XYZ：右 X 正、上 Y 正、朝你 Z 正
export const camera = new THREE.PerspectiveCamera(
  50, 
  window.innerWidth / window.innerHeight, 
  0.1, 
  1000
)
camera.position.set(5, 3, 6)

// 场景
export const scene = new THREE.Scene()
scene.background = new THREE.Color(SCENE_CONFIG.bgColor)

// 渲染器
export const renderer = new THREE.WebGLRenderer({ 
  antialias: true,      // 抗锯齿
  alpha: true           // 画布透明通道开关
})
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))   // 设备像素比，强制上限2
renderer.shadowMap.enabled = true   // 开启渲染器阴影计算
renderer.shadowMap.type = THREE.PCFSoftShadowMap   // 增强PCF滤波，柔和渐变
// 3D 画布容器：占据两个面板右侧的剩余空间
// 3D 画布容器：用 left + right:0 自动撑满剩余宽度
export const canvasContainer = document.createElement('div')
canvasContainer.id = 'canvas-container'
canvasContainer.style.cssText = `
  position: fixed;
  top: 16px;
  left: 0;
  right: 16px;
  bottom: 16px;
  z-index: 1;
  border-radius: 14px;
  overflow: hidden;
`
document.body.appendChild(canvasContainer)

// canvas 元素本身：absolute + 100% 填满父容器
renderer.domElement.style.display = 'block'
renderer.domElement.style.width = '100%'
renderer.domElement.style.height = '100%'
renderer.domElement.style.position = 'absolute'
renderer.domElement.style.left = '0'
renderer.domElement.style.top = '0'
canvasContainer.appendChild(renderer.domElement)

// 轨道控制器
export const controls = new OrbitControls(camera, renderer.domElement)
controls.enableDamping = true          // 阻尼总开关
controls.dampingFactor = 0.05          // 阻尼系数（惯性大小）0-1，后续必须在渲染循环更新控制器！
controls.minDistance = 5              // 缩放距离限制
controls.maxDistance = 500
controls.target.set(0, 0, 0)           // 环绕中心点

// 自适应窗口大小
export function handleResize() {
  const w = canvasContainer.clientWidth
  const h = canvasContainer.clientHeight
  if (w === 0 || h === 0) return
  
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  // false = 只改 Three.js 内部渲染分辨率，不改 CSS 尺寸
  renderer.setSize(w, h, false)
}

window.addEventListener('resize', handleResize)

// 渲染一帧
export function render() {
  renderer.render(scene, camera)
}