import test from 'node:test';
import assert from 'node:assert/strict';
import { request } from '../src/api.js';
import { authView } from '../src/layout.js';
import { readPreference, writePreference } from '../src/auth-screen.js';

test('disabled browser storage cannot prevent login or theme startup',()=>{
  const old=globalThis.localStorage;
  globalThis.localStorage={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');},removeItem(){throw Error('blocked');}};
  try{assert.equal(readPreference('vra-theme','light'),'light');assert.doesNotThrow(()=>writePreference('vra-login-username','engineer'));assert.doesNotThrow(()=>writePreference('vra-login-username',null));}finally{globalThis.localStorage=old;}
});
test('login supports password managers and preserves legacy numeric accounts while new passwords require 15 characters',()=>{
  const login=authView({}),register=authView({register:true});
  assert.match(login,/action="\/api\/auth\/login"/);
  assert.match(login,/autocomplete="current-password"/);
  assert.match(login,/name="remember_device" type="checkbox"/);
  const pattern=login.match(/name="username"[^>]*pattern="([^"]+)"/)[1];
  assert.equal(new RegExp('^(?:'+pattern+')$','v').test('125'),true);
  assert.match(register,/minlength="15"/);assert.match(register,/autocomplete="new-password"/);
  assert.doesNotMatch(register,/minlength="12"/);
});
test('an ambiguous write timeout is surfaced and never automatically repeated',async()=>{
  const old=globalThis.fetch;let calls=0;
  globalThis.fetch=async(_url,options)=>{calls++;return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));};
  try{await assert.rejects(request('/projects/p/model',{method:'PUT',body:'{}',timeoutMs:5}),e=>e.status===0&&e.ambiguous===true);assert.equal(calls,1);}finally{globalThis.fetch=old;}
});
test('rate-limit retry information reaches the UI without retrying a request',async()=>{
  const old=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({detail:'Wait before retrying'}),{status:429,headers:{'Retry-After':'900'}});};
  try{await assert.rejects(request('/auth/login',{method:'POST',body:'{}'}),e=>e.status===429&&e.retryAfter===900);assert.equal(calls,1);}finally{globalThis.fetch=old;}
});
