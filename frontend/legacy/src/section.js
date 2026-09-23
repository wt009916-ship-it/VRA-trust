// 详情页：墙体构造剖面展开动画（HTML/CSS 实现）
export function createSection(container, layers) {
  container.innerHTML = ''

  const row = document.createElement('div')
  row.style.cssText = `
    display: flex;
    align-items: stretch;
    justify-content: center;
    gap: 0;
    height: 100%;
    transition: gap 0.9s ease;
  `

  ;(layers || [])
    .filter(l => l.thickness > 0)
    .forEach(l => {
      const block = document.createElement('div')
      block.style.cssText = `
        position: relative;
        min-width: 72px;
        max-width: 190px;
        border-radius: 6px;
        background: #${l.color.toString(16).padStart(6, '0')};
        opacity: ${l.transparent ? 0.72 : 1};
        border: 1px solid rgba(15, 42, 38, 0.25);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 12px 18px;
        box-sizing: border-box;
        flex: 0 0 auto;
      `
      const name = document.createElement('div')
      name.textContent = l.name
      name.style.cssText = 'font-size: 13px; font-weight: 600; color: #1e293b; text-align: center; white-space: nowrap;'

      const info = document.createElement('div')
      info.textContent = `${(l.thickness * 1000).toFixed(0)} mm · λ ${l.lambda}`
      info.style.cssText = 'font-size: 11px; color: #475569; margin-top: 5px; text-align: center; white-space: nowrap;'

      block.appendChild(name)
      block.appendChild(info)
      row.appendChild(block)
    })

  container.appendChild(row)

  // 触发展开动画
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      row.style.gap = '22px'
    })
  })

  return {
    update() {},
    dispose() {
      container.innerHTML = ''
    }
  }
}
