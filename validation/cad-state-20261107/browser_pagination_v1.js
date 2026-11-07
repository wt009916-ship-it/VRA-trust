async(page)=>{
 const calls=[];
 const listener=r=>{if(r.url().endsWith('/cad-current-states'))calls.push(r.postDataJSON().cad_ids);};
 page.on('request',listener);
 try{
 await page.getByRole('button',{name:'CAD / BIM',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#cad-results [data-ifc-record]').length===20,{},{timeout:20000});
 const first=await page.locator('#cad-results [data-cad-record]').evaluateAll(rows=>rows.map(r=>r.dataset.cadRecord));
 if(first.length!==20||new Set(first).size!==20||!calls.some(ids=>ids.length===20&&ids.every(id=>first.includes(id))))throw Error('First page scope mismatch');
 await page.getByRole('button',{name:'下一页',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#cad-results [data-ifc-record]').length===1,{},{timeout:15000});
 const second=await page.locator('#cad-results [data-cad-record]').evaluateAll(rows=>rows.map(r=>r.dataset.cadRecord));
 if(second.length!==1||first.includes(second[0])||!calls.some(ids=>ids.length===1&&ids[0]===second[0]))throw Error('Second page scope mismatch');
 await page.getByRole('combobox',{name:'查看构件来源、数量与属性',exact:true}).selectOption('45');
 await page.waitForResponse(r=>r.url().endsWith('/cad-current-states')&&r.status()===200,{timeout:10000});
 if(await page.getByRole('combobox',{name:'查看构件来源、数量与属性',exact:true}).inputValue()!=='45')throw Error('Polling reset selection');
 await page.setViewportSize({width:390,height:844});
 const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
 if(width.document>width.viewport)throw Error('Mobile horizontal overflow');
 await page.locator('#cad-pager').screenshot({path:'output/playwright/cad-current-pager-mobile.png'});
 await page.locator('#cad-results').screenshot({path:'output/playwright/cad-current-detail-mobile.png'});
 return {total_records:new Set([...first,...second]).size,first_page:20,second_page:1,state_request_sizes:calls.map(x=>x.length),selection_preserved:true,width};
 }finally{page.off('request',listener);}
}
