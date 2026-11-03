import test from 'node:test';
import assert from 'node:assert/strict';
import {post} from '../src/api.js';

test('3000 concurrent identical submissions share one actual request and release the lock',async()=>{
  const original=globalThis.fetch;let release,calls=0;
  const gate=new Promise(resolve=>{release=resolve;});
  globalThis.fetch=async()=>{calls++;await gate;return {ok:true,status:200,json:async()=>({saved:true})};};
  try{
    const submitted=Array.from({length:3000},()=>post('/pressure-test',{value:1}));
    assert.equal(calls,1);release();const result=await Promise.all(submitted);
    assert.equal(result.length,3000);assert.ok(result.every(v=>v.saved));
    await post('/pressure-test',{value:1});assert.equal(calls,2);
  }finally{globalThis.fetch=original;}
});
