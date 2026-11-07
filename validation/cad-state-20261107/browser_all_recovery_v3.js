async(page)=>{
 let fresh=0;
 const listener=r=>{if(/\/cad-inspections\/cad_[a-f0-9]{32}$/.test(r.url()))fresh++;};
 page.on('request',listener);
 try{
 await page.getByRole('button',{name:'立即核验状态',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#cad-results [data-ifc-record]').length===20,{},{timeout:15000});
 if(fresh<20)throw Error('Page recovery did not freshly read twenty records: '+fresh);
 await page.getByRole('button',{name:'下一页',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#cad-results [data-ifc-record]').length===1,{},{timeout:15000});
 return {recovered_first_page:20,minimum_fresh_detail_requests:20,observed_requests:fresh,recovered_second_page:1};
 }finally{page.off('request',listener);}
}
