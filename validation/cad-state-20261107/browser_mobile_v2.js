async(page)=>{
 const cid='cad_970df543018e4224b1debafcb76a5415';
 const quantity=page.locator('[data-ifc-detail="'+cid+'"] p').filter({hasText:'体积 24 m³'});
 await quantity.scrollIntoViewIfNeeded();
 await quantity.screenshot({path:'output/playwright/cad-current-quantity-mobile.png'});
 await page.screenshot({path:'output/playwright/cad-current-viewport-mobile.png'});
 return {viewport:await page.evaluate(()=>innerWidth),quantity_text:await quantity.innerText(),screenshot_scope:'visible viewport and actual quantity paragraph; whole tall article is clipped by scrolling workspace'};
}
