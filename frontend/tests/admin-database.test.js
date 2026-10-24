import test from 'node:test';
import assert from 'node:assert/strict';
import { cell } from '../src/admin-database.js';

test('database cells preserve unknown/zero and escape source records',()=>{
  assert.equal(cell(null,'revision'),'—');
  assert.equal(cell(0,'revision'),'0');
  assert.equal(cell(false,'disabled'),'否');
  assert.equal(cell(true,'disabled'),'是');
  assert.equal(cell('<img onerror=alert(1)>','name'),'&lt;img onerror=alert(1)&gt;');
  assert.ok(!cell({note:'<script>alert(1)</script>'},'data').includes('<script>'));
});
