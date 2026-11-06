const fs=require('node:fs/promises');
module.exports=async(page)=>{
 const region=page.getByRole('region',{name:'天气输入检查',exact:true});
 if(!(await region.innerText()).includes('不证明无雨'))await region.getByText('4 类缺测或推导条件，需复核',{exact:true}).click();
 await region.scrollIntoViewIfNeeded();
 const text=await region.innerText();
 if(!text.includes('不证明无雨'))throw Error('Missing weather conditions');
 await page.screenshot({path:'output/playwright/weather-20261107/report-weather-v2-retry.png'});
 const [report]=await Promise.all([page.waitForEvent('popup'),page.getByRole('link',{name:'完整 JSON ↗',exact:true}).click()]);
 await report.waitForLoadState();
 const value=JSON.parse(await report.locator('body').innerText());
 if(value.run.status!=='succeeded'||value.run.weather_quality.conditions.length!==4)throw Error('Invalid browser report');
 await fs.writeFile('output/playwright/weather-20261107/report.json',JSON.stringify(value,null,2));
 await report.close();
};
