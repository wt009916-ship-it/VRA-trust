async page => {
 const region=page.getByRole('region',{name:'多墙材料包络计量',exact:true});
 await region.getByRole('heading',{name:'材料包络量未知',exact:true}).waitFor({timeout:15000});
 if(await region.getByRole('table').count())throw Error('Stale amounts remain visible');
 const article=region.locator('article');
 await article.scrollIntoViewIfNeeded();
 await article.screenshot({path:'D:/稀土agent-稀土制暖全流程/output/playwright/material-collection-stale-mobile.png'});
 return {staleAmountsWithdrawn:true,text:await article.innerText(),layout:await region.evaluate(el=>({
  client:el.clientWidth,scroll:el.scrollWidth,rect:el.getBoundingClientRect().toJSON(),
  children:[...el.children].map(x=>({tag:x.tagName,width:x.getBoundingClientRect().width,scroll:x.scrollWidth}))}))};
}
