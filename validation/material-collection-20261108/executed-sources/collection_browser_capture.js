async page => {
 const region=page.getByRole('region',{name:'多墙材料包络计量',exact:true});
 await region.scrollIntoViewIfNeeded();
 await region.screenshot({path:'D:/稀土agent-稀土制暖全流程/output/playwright/material-collection-desktop.png'});
 const link=region.getByRole('link',{name:'材料计量与来源报告',exact:true});
 const [report]=await Promise.all([page.waitForEvent('popup'),link.click()]);
 await report.getByRole('heading',{name:'多构件材料包络计量',exact:true}).waitFor();
 const verified=await report.getByRole('table').innerText();
 await report.close();
 await page.setViewportSize({width:390,height:844});
 await region.scrollIntoViewIfNeeded();
 await region.screenshot({path:'D:/稀土agent-稀土制暖全流程/output/playwright/material-collection-mobile.png'});
 const layout=await page.evaluate(()=>({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth}));
 if(layout.documentWidth>layout.viewport+1)throw Error('Page-level horizontal overflow: '+JSON.stringify(layout));
 return {reportOpened:true,reportTable:verified,mobile:layout};
}
