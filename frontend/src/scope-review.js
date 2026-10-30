import {storeyKey} from './solid-preview.js';

export function reviewUseScope(rooms,{storey='',conditioned,include_floor_area,note}){
  if(typeof note!=='string'||note.trim().length<10)throw Error('批量确认须填写至少10字符的范围与用途依据。');
  if(conditioned===undefined&&include_floor_area===undefined)throw Error('至少选择一项需要修改的属性。');
  for(const value of [conditioned,include_floor_area])if(value!==undefined&&value!==null&&typeof value!=='boolean')throw Error('用途属性无效。');
  const next=structuredClone(rooms),affected=[];
  for(const room of next){
    if(storey&&storeyKey(room)!==storey)continue;
    if(conditioned!==undefined)room.conditioned=conditioned;
    if(include_floor_area!==undefined)room.include_floor_area=include_floor_area;
    affected.push(room.id);
  }
  if(!affected.length)throw Error('当前显示范围没有空间。');
  return {rooms:next,affected,note:`批量用途确认（${storey||'全楼'}，${affected.length}空间）：${note.trim()}`};
}
