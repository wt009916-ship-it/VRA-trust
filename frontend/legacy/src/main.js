import './style.css'
import { handleResize, controls, render, canvasContainer } from './scene.js'
import './lights.js'
import './ground.js'
import { initTooltip } from './tooltip.js'
import { loadDashboard, initDragDrop } from './jsonLoader.js'
import { renderHome, updateThumbnails, resizeThumbnails } from './home.js'
import { renderDetail } from './detail.js'
import { exportReport } from './reportExporter.js'
import { state } from './config.js'
import { updateEntrance } from './animation.js'
import dashboardData from '../../../fixtures/demo/frontend-data/dashboard_data.json'
import { ensureChartsFit } from './charts.js'
import { mountWorkbench } from './workbench.js'
import { updateRunStatusUI } from './runStatus.js'

// ===================== 开始界面 =====================

function createStartScreen() {
  const startScreen = document.createElement('div')
  startScreen.id = 'start-screen'
  startScreen.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: linear-gradient(135deg, #e6f7f5 0%, #c5f5e8 50%, #a8e6e0 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 99999;
    transition: opacity 0.7s ease;
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  `
  
  startScreen.innerHTML = `
    <!-- 1. 六边形科技网格 -->
    <div style="
      position: absolute;
      inset: 0;
      opacity: 0.35;
      background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2228%22 height=%2249%22 viewBox=%220 0 28 49%22><path fill=%22none%22 stroke=%22rgba(33,171,165,0.15)%22 stroke-width=%221%22 d=%22M13.99 9.25l13 7.5v15l-13 7.5L1 31.75v-15l12.99-7.5zM14 1v8.5M14 39.5v8.5M1 16.25l13 7.5M27 16.25l-13 7.5%22/></svg>');
      background-size: 28px 49px;
      pointer-events: none;
    "></div>
    
    <!-- 2. 对角线光束 -->
    <div style="
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: conic-gradient(from 0deg at 50% 50%, transparent 0deg, rgba(33,171,165,0.04) 60deg, transparent 120deg);
      animation: rotate 20s linear infinite;
      pointer-events: none;
    "></div>
    
    <!-- 3. 中心柔和光晕 -->
    <div style="
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 600px;
      height: 600px;
      background: radial-gradient(circle, rgba(33,171,165,0.12) 0%, transparent 70%);
      pointer-events: none;
    "></div>
    
    <!-- 4. 脉冲光环（呼吸灯） -->
    <div style="
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 360px;
      height: 360px;
      border: 1px solid rgba(33,171,165,0.15);
      border-radius: 50%;
      animation: pulse 3s ease-in-out infinite;
      pointer-events: none;
    "></div>
    <div style="
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 460px;
      height: 460px;
      border: 1px solid rgba(33,171,165,0.08);
      border-radius: 50%;
      animation: pulse 3s ease-in-out infinite 1s;
      pointer-events: none;
    "></div>
    
    <!-- 5. HUD 四角定位框 -->
    <div style="position: absolute; top: 40px; left: 40px; width: 40px; height: 40px; pointer-events: none;">
      <div style="position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: rgba(33,171,165,0.4);"></div>
      <div style="position: absolute; top: 0; left: 0; width: 2px; height: 100%; background: rgba(33,171,165,0.4);"></div>
    </div>
    <div style="position: absolute; top: 40px; right: 40px; width: 40px; height: 40px; pointer-events: none;">
      <div style="position: absolute; top: 0; right: 0; width: 100%; height: 2px; background: rgba(33,171,165,0.4);"></div>
      <div style="position: absolute; top: 0; right: 0; width: 2px; height: 100%; background: rgba(33,171,165,0.4);"></div>
    </div>
    <div style="position: absolute; bottom: 40px; left: 40px; width: 40px; height: 40px; pointer-events: none;">
      <div style="position: absolute; bottom: 0; left: 0; width: 100%; height: 2px; background: rgba(33,171,165,0.4);"></div>
      <div style="position: absolute; bottom: 0; left: 0; width: 2px; height: 100%; background: rgba(33,171,165,0.4);"></div>
    </div>
    <div style="position: absolute; bottom: 40px; right: 40px; width: 40px; height: 40px; pointer-events: none;">
      <div style="position: absolute; bottom: 0; right: 0; width: 100%; height: 2px; background: rgba(33,171,165,0.4);"></div>
      <div style="position: absolute; bottom: 0; right: 0; width: 2px; height: 100%; background: rgba(33,171,165,0.4);"></div>
    </div>
    
    <!-- 6. 顶部状态栏装饰 -->
    <div style="
      position: absolute;
      top: 32px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      align-items: center;
      gap: 12px;
      pointer-events: none;
    ">
      <div style="width: 6px; height: 6px; background: #21aba5; border-radius: 50%; animation: blink 2s ease-in-out infinite;"></div>
      <div style="font-size: 11px; color: rgba(33,171,165,0.6); letter-spacing: 3px; font-family: monospace;">SYSTEM READY</div>
      <div style="width: 80px; height: 1px; background: linear-gradient(90deg, rgba(33,171,165,0.4), transparent);"></div>
    </div>
    
    <!-- 7. 浮动几何粒子 -->
    <div style="position: absolute; top: 15%; left: 12%; width: 40px; height: 40px; border: 2px solid rgba(33,171,165,0.25); border-radius: 8px; animation: float 6s ease-in-out infinite; pointer-events: none;"></div>
    <div style="position: absolute; top: 22%; right: 15%; width: 24px; height: 24px; background: rgba(33,171,165,0.15); border-radius: 50%; animation: float 8s ease-in-out infinite 1s; pointer-events: none;"></div>
    <div style="position: absolute; bottom: 28%; left: 18%; width: 16px; height: 16px; border: 2px solid rgba(33,171,165,0.2); transform: rotate(45deg); animation: float 7s ease-in-out infinite 0.5s; pointer-events: none;"></div>
    <div style="position: absolute; bottom: 20%; right: 12%; width: 56px; height: 56px; border: 1.5px solid rgba(33,171,165,0.15); border-radius: 50%; animation: float 9s ease-in-out infinite 2s; pointer-events: none;"></div>
    
    <!-- 8. 底部建筑剪影（玻璃幕墙城市） -->
    <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 180px; pointer-events: none; filter: drop-shadow(0 -6px 24px rgba(33,171,165,0.2));">
      <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 180px; transform: scaleY(-1); opacity: 0.06; filter: blur(3px); display: flex; align-items: flex-end; justify-content: center; gap: 4px; padding: 0 10%; mask-image: linear-gradient(to top, black, transparent); -webkit-mask-image: linear-gradient(to top, black, transparent);">
        <div style="width:28px; height:60px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:40px; height:110px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:32px; height:80px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:52px; height:140px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:36px; height:95px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:44px; height:125px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:30px; height:70px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:48px; height:155px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:34px; height:85px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:42px; height:115px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:26px; height:55px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
        <div style="width:38px; height:100px; background:#1f7974; border-radius:2px 2px 0 0;"></div>
      </div>
      <div style="display: flex; align-items: flex-end; justify-content: center; gap: 4px; padding: 0 10%; height: 180px; position: relative;">
        <div style="width:28px; height:60px; background:linear-gradient(180deg, rgba(33,171,165,0.45) 0%, rgba(15,42,38,0.55) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.5); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 10px, rgba(255,255,255,0.06) 10px, rgba(255,255,255,0.06) 11px);"></div></div>
        <div style="width:40px; height:110px; background:linear-gradient(180deg, rgba(33,171,165,0.5) 0%, rgba(15,42,38,0.6) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.5); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 8px, rgba(255,255,255,0.08) 8px, rgba(255,255,255,0.08) 9px), repeating-linear-gradient(90deg, transparent, transparent 10px, rgba(255,255,255,0.05) 10px, rgba(255,255,255,0.05) 11px);"></div></div>
        <div style="width:32px; height:80px; background:linear-gradient(180deg, rgba(33,171,165,0.4) 0%, rgba(15,42,38,0.5) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.45); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 12px, rgba(255,255,255,0.06) 12px, rgba(255,255,255,0.06) 13px);"></div></div>
        <div style="width:52px; height:140px; background:linear-gradient(180deg, rgba(33,171,165,0.55) 0%, rgba(15,42,38,0.65) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.55); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 7px, rgba(255,255,255,0.1) 7px, rgba(255,255,255,0.1) 8px), repeating-linear-gradient(90deg, transparent, transparent 8px, rgba(255,255,255,0.06) 8px, rgba(255,255,255,0.06) 9px);"></div></div>
        <div style="width:36px; height:95px; background:linear-gradient(180deg, rgba(33,171,165,0.42) 0%, rgba(15,42,38,0.52) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.45); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 9px, rgba(255,255,255,0.07) 9px, rgba(255,255,255,0.07) 10px);"></div></div>
        <div style="width:44px; height:125px; background:linear-gradient(180deg, rgba(33,171,165,0.48) 0%, rgba(15,42,38,0.58) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.5); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 8px, rgba(255,255,255,0.09) 8px, rgba(255,255,255,0.09) 9px), repeating-linear-gradient(90deg, transparent, transparent 10px, rgba(255,255,255,0.05) 10px, rgba(255,255,255,0.05) 11px);"></div></div>
        <div style="width:30px; height:70px; background:linear-gradient(180deg, rgba(33,171,165,0.38) 0%, rgba(15,42,38,0.48) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.4); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 11px, rgba(255,255,255,0.06) 11px, rgba(255,255,255,0.06) 12px);"></div></div>
        <div style="width:48px; height:155px; background:linear-gradient(180deg, rgba(33,171,165,0.6) 0%, rgba(15,42,38,0.7) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.6); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 6px, rgba(255,255,255,0.12) 6px, rgba(255,255,255,0.12) 7px), repeating-linear-gradient(90deg, transparent, transparent 7px, rgba(255,255,255,0.07) 7px, rgba(255,255,255,0.07) 8px);"></div></div>
        <div style="width:34px; height:85px; background:linear-gradient(180deg, rgba(33,171,165,0.4) 0%, rgba(15,42,38,0.5) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.45); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 10px, rgba(255,255,255,0.07) 10px, rgba(255,255,255,0.07) 11px);"></div></div>
        <div style="width:42px; height:115px; background:linear-gradient(180deg, rgba(33,171,165,0.46) 0%, rgba(15,42,38,0.56) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.48); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 8px, rgba(255,255,255,0.08) 8px, rgba(255,255,255,0.08) 9px), repeating-linear-gradient(90deg, transparent, transparent 9px, rgba(255,255,255,0.05) 9px, rgba(255,255,255,0.05) 10px);"></div></div>
        <div style="width:26px; height:55px; background:linear-gradient(180deg, rgba(33,171,165,0.35) 0%, rgba(15,42,38,0.45) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.4); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 12px, rgba(255,255,255,0.05) 12px, rgba(255,255,255,0.05) 13px);"></div></div>
        <div style="width:38px; height:100px; background:linear-gradient(180deg, rgba(33,171,165,0.44) 0%, rgba(15,42,38,0.54) 100%); border-radius:2px 2px 0 0; border-top:1.5px solid rgba(255,255,255,0.48); position:relative; overflow:hidden;"><div style="position:absolute; inset:0; background:repeating-linear-gradient(0deg, transparent, transparent 9px, rgba(255,255,255,0.07) 9px, rgba(255,255,255,0.07) 10px);"></div></div>
      </div>
    </div>
    
    <!-- 9. 底部地平线光带 -->
    <div style="position: absolute; bottom: 178px; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, transparent, rgba(33,171,165,0.5), rgba(255,255,255,0.6), rgba(33,171,165,0.5), transparent); box-shadow: 0 0 12px rgba(33,171,165,0.3); pointer-events: none;"></div>
    
    <!-- 主内容 -->
    <div style="text-align: center; position: relative; z-index: 2; animation: fadeInUp 0.8s ease;">
      <div style="
        width: 80px; 
        height: 80px; 
        background: rgba(33,171,165,0.08); 
        border-radius: 20px; 
        margin: 0 auto 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(33,171,165,0.2);
      ">
        <div style="width: 40px; height: 40px; background: #21aba5; border-radius: 10px; opacity: 0.9;"></div>
      </div>
      <h1 style="font-size: 52px; font-weight: 700; margin-bottom: 12px; letter-spacing: 6px; color: #0f2a26;">
        稀土智暖
      </h1>
      <p style="font-size: 16px; color: #1f7974; margin-bottom: 8px; letter-spacing: 2px;">
        建筑墙体保温方案三维可视化对比系统
      </p>
      <p style="font-size: 13px; color: #64a89e; margin-bottom: 48px;">
        3D Visualization & Comparison of Wall Insulation Schemes
      </p>
      <button id="start-btn" style="
        padding: 16px 56px;
        font-size: 17px;
        font-weight: 600;
        color: #fff;
        background: #21aba5;
        border: none;
        border-radius: 30px;
        cursor: pointer;
        box-shadow: 0 8px 32px rgba(33,171,165,0.35);
        transition: all 0.3s ease;
        letter-spacing: 2px;
      ">
        点击进入
      </button>
      <p style="font-size: 11px; color: #94a3b8; margin-top: 24px;">
        支持拖拽 JSON 文件加载自定义方案
      </p>
    </div>
    
    <style>
      @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes float {
        0%, 100% { transform: translateY(0) rotate(0deg); }
        50% { transform: translateY(-20px) rotate(5deg); }
      }
      @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      @keyframes pulse {
        0%, 100% { transform: translate(-50%, -50%) scale(1); opacity: 0.6; }
        50% { transform: translate(-50%, -50%) scale(1.08); opacity: 0.2; }
      }
      @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
      }
    </style>
  `
  
  document.body.appendChild(startScreen)
  
  const btn = document.getElementById('start-btn')
  
  btn.addEventListener('mouseenter', () => {
    btn.style.transform = 'scale(1.05)'
    btn.style.boxShadow = '0 12px 40px rgba(33,171,165,0.45)'
  })
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = 'scale(1)'
    btn.style.boxShadow = '0 8px 32px rgba(33,171,165,0.35)'
  })
  
  btn.addEventListener('click', () => {
    // 点击瞬间才开始加载数据、创建3D模型
    state.dataMode = 'demo'
    state.runMeta = null
    state.validatedComparison = null
    loadDashboard(dashboardData, 'B')
    navigateTo('home', 'B')
    
    startScreen.style.opacity = '0'
    setTimeout(() => {
      startScreen.remove()
    }, 700)
  })
}

// 先创建开始界面（盖住所有内容）
createStartScreen()

// ===================== 视图与路由 =====================

function createViews() {
  const home = document.createElement('div')
  home.id = 'view-home'

  const detail = document.createElement('div')
  detail.id = 'view-detail'
  detail.style.display = 'none'

  document.body.appendChild(home)
  document.body.appendChild(detail)
}

function layoutMainCanvas() {
  const host = document.getElementById('detail-3d')
  if (!host) return
  if (canvasContainer.parentNode !== host) {
    host.appendChild(canvasContainer)
  }
  Object.assign(canvasContainer.style, {
    position: 'absolute',
    top: '0',
    left: '0',
    width: '100%',
    height: '100%',
    right: 'auto',
    bottom: 'auto',
    zIndex: '1',
    borderRadius: '12px',
    display: 'block'
  })
  handleResize()
}

function navigateTo(view, planKey) {
  state.view = view
  const home = document.getElementById('view-home')
  const detail = document.getElementById('view-detail')

  if (view === 'home') {
    home.style.display = 'block'
    detail.style.display = 'none'
    canvasContainer.style.display = 'none'
    renderHome(state.dashboardData, planKey || state.currentPlanKey)
  } else {
    home.style.display = 'none'
    detail.style.display = 'block'
    layoutMainCanvas()
    renderDetail(state.dashboardData, planKey || state.currentPlanKey)
  }
}

window.navigateTo = navigateTo
window.navigateToDetail = planKey => {
  if (state.dataMode === 'live' && (!state.dashboardData || state.runMeta?.status !== 'succeeded')) return
  loadDashboard(state.dashboardData || dashboardData, planKey)
  navigateTo('detail', planKey)
  updateRunStatusUI(state.runMeta)
}
window.selectScheme = key => {
  if (state.dataMode === 'live' && !state.dashboardData) return
  loadDashboard(state.dashboardData || dashboardData, key)
}
window.exportDetailPDF = () => exportReport()

createViews()

initTooltip()
initDragDrop()

window.addEventListener('resize', () => {
  handleResize()
  resizeThumbnails()
})

// ===================== 渲染循环 =====================
function animate() {
  requestAnimationFrame(animate)
  updateEntrance()
  controls.update()
  render()
  if (state.view === 'home') updateThumbnails()
  ensureChartsFit()
}
animate()
mountWorkbench()
