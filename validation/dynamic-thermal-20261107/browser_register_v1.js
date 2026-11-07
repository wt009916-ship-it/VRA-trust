async (page) => {
  await page.getByRole('textbox', {name: '怎么称呼你', exact: true}).fill('逐时热工本地验收');
  await page.getByRole('textbox', {name: '用户名', exact: true}).fill('hourly_thermal_ui');
  const password = await page.evaluate(() => crypto.randomUUID() + crypto.randomUUID());
  await page.getByRole('textbox', {name: '密码 显示密码', exact: true}).fill(password);
  await page.getByRole('button', {name: '创建工作区', exact: true}).click();
  await page.getByRole('button', {name: '创建参考项目', exact: true}).waitFor({timeout: 15000});
  return {registered_in_isolated_database: true, credentials_saved: false};
}
