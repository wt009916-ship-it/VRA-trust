module.exports=async(page)=>{
 const scheme=page.getByRole('combobox',{name:'方案',exact:true}),button=page.getByRole('button',{name:'运行仿真',exact:true});
 for(const value of ['R1','baseline']){
  await scheme.selectOption(value);
  await page.getByRole('status').filter({hasText:'当前方案通过输入准入'}).waitFor();
  if(await button.isDisabled())throw Error('Valid scheme is disabled');
 }
 await button.click();
};
