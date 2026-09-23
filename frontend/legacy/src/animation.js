import { SCENE_CONFIG, state } from './config.js'

// ===================== 入场动画 =====================

// 用 let 不用 const，因为后续要不断修改数值
// 全局变量，入场总进度 0-1

/**
 * 更新入场动画
 * 每帧调用
 */
export function updateEntrance() {
  if (state.entranceProgress >= 1) return
  state.entranceProgress = Math.min(1, state.entranceProgress + SCENE_CONFIG.animSpeed)

  // easeOutCubic（三次缓出），整栋建筑从原点生长
  const ease = 1 - Math.pow(1 - state.entranceProgress, 3)
  if (state.buildingGroup) {
    state.buildingGroup.scale.set(ease, ease, ease)
  }
}

/**
 * 重置入场动画
 */
export function resetEntrance() {
  state.entranceProgress = 0
  if (state.buildingGroup) {
    state.buildingGroup.scale.set(0, 0, 0)
  }
}
