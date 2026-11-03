import test from 'node:test';
import assert from 'node:assert/strict';
import { request, setCsrfToken } from '../src/api.js';

test('a delayed old-session 401 cannot invalidate a newly authenticated session',async()=>{
  const oldFetch=globalThis.fetch,oldDocument=globalThis.document;let finish,events=0;
  globalThis.document={dispatchEvent(){events++;}};
  globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});
  try{setCsrfToken('old-session');const pending=request('/projects');setCsrfToken('new-session');finish(new Response(JSON.stringify({detail:'expired'}),{status:401}));await assert.rejects(pending,e=>e.status===401);assert.equal(events,0);}finally{setCsrfToken('');globalThis.fetch=oldFetch;globalThis.document=oldDocument;}
});


test('a cross-tab CSRF change requests identity refresh without replaying a write',async()=>{
  const oldFetch=globalThis.fetch,oldDocument=globalThis.document;let calls=0,eventType;
  globalThis.document={dispatchEvent(event){eventType=event.type;}};
  globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({detail:'会话校验失败，请刷新后重试'}),{status:403});};
  try{await assert.rejects(request('/projects/p/model',{method:'PUT',body:'{}'}),e=>e.status===403);assert.equal(eventType,'session-refresh-required');assert.equal(calls,1);}finally{globalThis.fetch=oldFetch;globalThis.document=oldDocument;}
});
