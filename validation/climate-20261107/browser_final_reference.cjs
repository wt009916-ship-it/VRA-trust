module.exports=async(page)=>{
 await page.reload();await page.getByRole('button',{name:'探索参考项目',exact:true}).click();
 await page.getByRole('button',{name:'资料 4',exact:true}).waitFor();
 await page.getByRole('button',{name:'资料 4',exact:true}).click();
 await page.getByRole('button',{name:'确认待审模型与天气',exact:true}).click();
};
