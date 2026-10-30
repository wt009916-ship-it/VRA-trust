import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
export default {plugins:[{name:'local-console-boundary',enforce:'pre',resolveId(source){
 if(source==='virtual:local-console')return process.env.VRA_PUBLIC_BUILD!=='1'&&existsSync(fileURLToPath(new URL('./src/admin-ui.js',import.meta.url)))?fileURLToPath(new URL('./src/admin-ui.js',import.meta.url)):'\0public-console';
},load(id){if(id==='\0public-console')return `export async function adminWorkspace(root){root.textContent='此公开发行包未包含私有开发者后台。';}`;}}]};
