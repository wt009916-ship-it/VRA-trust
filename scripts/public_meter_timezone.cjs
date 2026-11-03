const fs=require('node:fs');
const {zones,dates}=JSON.parse(fs.readFileSync(0,'utf8'));
const result={};
for(const timeZone of zones){
  const format=new Intl.DateTimeFormat('en-US',{timeZone,timeZoneName:'longOffset'});
  result[timeZone]=[...new Set(dates.map(value=>{
    const offset=format.formatToParts(new Date(value+'Z')).find(p=>p.type==='timeZoneName').value;
    if(offset==='GMT')return 0;
    const match=/^GMT([+-])(\d{2}):(\d{2})$/.exec(offset);if(!match)throw Error(offset);
    return (match[1]==='-'?-1:1)*(Number(match[2])*60+Number(match[3]));
  }))];
}
process.stdout.write(JSON.stringify(result));
