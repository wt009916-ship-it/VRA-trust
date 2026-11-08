async page => {
 const region=page.getByRole('region',{name:'多墙材料包络计量',exact:true});
 await region.getByRole('listbox',{name:'参与计量的构件（可多选）'}).selectOption(['4131','4598','4643','5106']);
 await region.getByRole('button',{name:'核算材料包络',exact:true}).click();
 await region.getByRole('heading',{name:'材料包络去重结果',exact:true}).waitFor({timeout:60000});
 return {submitted:true,visibleText:await region.innerText()};
}
