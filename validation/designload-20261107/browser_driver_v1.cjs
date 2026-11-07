// Local acceptance only. No credentials are printed, saved in receipts, or sent externally.
const {chromium}=require('C:/Users/18483/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright');
const fs=require('node:fs/promises'),readline=require('node:readline');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(15000);const harnessErrors=[];const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:18774/');
 await page.getByRole('button',{name:'创建工作区',exact:true}).waitFor();
 await page.getByRole('textbox',{name:'怎么称呼你',exact:true}).fill('分区负荷隔离验收');
 await page.getByRole('textbox',{name:'用户名',exact:true}).fill('design_load_ui_test');
 let password=require('node:crypto').randomBytes(24).toString('hex');
 await page.getByRole('textbox',{name:'密码 显示密码',exact:true}).fill(password);
 await page.getByRole('button',{name:'创建工作区',exact:true}).click();
 password=null;
 await page.getByRole('button',{name:'创建工作区',exact:true}).waitFor({state:'hidden'});
 console.log(JSON.stringify({ready:true,credential_file_created:false,snapshot:await page.locator('body').innerText()}));
 const input=readline.createInterface({input:process.stdin,terminal:false});
 for await(const line of input){
  try{
   const c=JSON.parse(line);
   if(c.action==='close'){await browser.close();console.log(JSON.stringify({closed:true,errors}));input.close();process.stdin.destroy();break;}
   if(c.action==='click')await page.getByRole(c.role||'button',{name:c.name,exact:true}).nth(c.index||0).click();
   if(c.action==='script')await require(require('node:path').resolve(c.path))(page);
   if(c.action==='fill')await page.getByRole(c.role||'textbox',{name:c.name,exact:true}).fill(c.value);
   if(c.action==='upload')await page.getByLabel(c.name,{exact:true}).setInputFiles(c.path);
   if(c.action==='wait')await page.getByText(c.name,{exact:true}).waitFor();
   if(c.action==='scroll')await page.getByRole(c.role,{name:c.name,exact:true}).scrollIntoViewIfNeeded();
   if(c.action==='report'){
    const [report]=await Promise.all([page.waitForEvent('popup'),page.getByRole('link',{name:c.name,exact:true}).click()]);
    await report.waitForLoadState();const text=await report.locator('body').innerText();await fs.writeFile(c.path,text);console.log(JSON.stringify({report:text}));await report.close();
   }
   if(c.action==='select')await page.getByRole('combobox',{name:c.name,exact:true}).selectOption(c.value);
   if(c.action==='screenshot')await page.screenshot({path:c.path,fullPage:false});
   const result={url:page.url(),snapshot:await page.locator('body').innerText(),aria:await page.locator('body').ariaSnapshot(),errors};
   if(c.save)await fs.writeFile(c.save,JSON.stringify(result,null,2));
   console.log(JSON.stringify(c.compact?{action:c.action,done:true,errors}:result));
  }catch(e){harnessErrors.push({error:e.message,snapshot:await page.locator('body').innerText().catch(()=>null)});await fs.writeFile('output/playwright/designload-20261107/harness-errors.json',JSON.stringify(harnessErrors,null,2));console.log(JSON.stringify({error:e.message}));}
 }
})().catch(e=>{console.error('UI acceptance failed: '+e.message);process.exit(1);});


