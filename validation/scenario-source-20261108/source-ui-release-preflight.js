async (page) => {
 await page.__releasePreflight();
 await page.getByText('本次未提交；请先解决来源核验问题。',{exact:true}).waitFor();
 if(page.__sourcePosts.length)throw Error('Source changed but POST occurred');
 if(await page.getByRole('textbox',{name:'方案一名称',exact:true}).inputValue()!=='保留我的方案草稿')throw Error('Draft lost');
 await page.getByRole('heading',{name:'从多构件去重材料建立两套方案',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/preflight-blocked.png'});
}
