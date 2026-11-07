async (page) => {
  const before = await page.evaluate(async () => ({hidden: document.hidden, visibility: document.visibilityState,
    animationFrame: await Promise.race([new Promise(r => requestAnimationFrame(() => r(true))), new Promise(r => setTimeout(() => r(false), 500))])}));
  await page.bringToFront();
  const after = await page.evaluate(async () => ({hidden: document.hidden, visibility: document.visibilityState,
    animationFrame: await Promise.race([new Promise(r => requestAnimationFrame(() => r(true))), new Promise(r => setTimeout(() => r(false), 500))])}));
  let clickError = null;
  try { await page.getByRole('button', {name:'探索参考项目',exact:true}).click({timeout:3000}); }
  catch(error) {
    clickError = String(error);
    await page.getByRole('button', {name:'探索参考项目',exact:true}).focus();
    await page.keyboard.press('Enter');
  }
  await page.getByRole('button',{name:'运行仿真',exact:true}).waitFor({state:'attached',timeout:15000}).catch(() => {});
  return {before,after,clickError};
}
