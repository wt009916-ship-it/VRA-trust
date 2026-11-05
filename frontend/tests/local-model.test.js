import test from 'node:test';
import assert from 'node:assert/strict';
import { localModelMarkup } from '../src/trust-ui.js';

test('local model setup escapes names, exposes no credential input, and distinguishes readiness', () => {
  const html=localModelMarkup({model:'"><img onerror="x">',port:18773,enabled:false,key_configured:false});
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('name="api_key"'));
  assert.ok(html.includes('配置就绪不等于连通或工程能力通过验收'));
  assert.ok(html.includes('访问令牌未配置'));
});
