const fs=require('node:fs/promises');
module.exports=async(page)=>{
 const cases=JSON.parse(await fs.readFile('validation/climate-20261107/preflight-probe.json','utf8')).cases;
 const item=cases.find(x=>x.case==='dry_bulb_missing');if(!item)throw Error('Missing preserved counterexample');
 await page.getByLabel('文件',{exact:true}).setInputFiles(item.path);
 await page.getByRole('combobox',{name:'证据类型',exact:true}).selectOption({label:'EPW 天气'});
 await page.getByRole('textbox',{name:'来源定位',exact:true}).fill('第9行干球99.9缺测；保留原始反例文件');
 await page.getByRole('textbox',{name:'来源与权威性',exact:true}).fill('公开Golden参考天气的隔离变异反例；不是观测天气');
 await page.getByRole('textbox',{name:'使用授权 / 许可',exact:true}).fill('用户授权公开参考与合成本地验收');
 await page.getByRole('textbox',{name:'登记人',exact:true}).fill('隔离天气验收');
 await page.getByRole('textbox',{name:'不确定性说明',exact:true}).fill('故意引入关键温度缺测，必须拒绝计算，不能视为已修复');
 await page.getByRole('button',{name:'保存文件和证据记录',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
};
