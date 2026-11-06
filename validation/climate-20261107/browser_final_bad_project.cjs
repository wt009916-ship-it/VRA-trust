const fs=require('node:fs/promises');
module.exports=async(page)=>{
 const report=JSON.parse(await fs.readFile('output/playwright/weather-20261107/report.json','utf8'));
 await page.locator('button[data-project="'+report.project.project_id+'"]').click();
 await page.getByRole('button',{name:'资料 5',exact:true}).waitFor();
 await page.getByRole('button',{name:'仿真',exact:true}).click();
};
