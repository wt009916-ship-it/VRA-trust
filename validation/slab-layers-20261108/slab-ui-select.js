async (page) => {
  const panel = page.getByRole('region', {name: '多构件材料包络计量', exact: true});
  await panel.getByRole('listbox').selectOption(['5165', '6132']);
  await panel.getByRole('button', {name: '核算材料包络', exact: true}).click();
  await page.getByRole('heading', {name: '材料包络去重结果', exact: true}).waitFor({timeout: 60000});
  console.log(await panel.innerText());
}
