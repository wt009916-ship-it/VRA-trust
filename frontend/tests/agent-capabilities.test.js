import test from 'node:test';
import assert from 'node:assert/strict';
import {capabilityMarkup} from '../src/agent-capabilities.js';

test('capability scope remains separate from project readiness and certification',()=>{
 const html=capabilityMarkup({capability_assessments:[{title:'结构安全认证',capability_id:'structural_safety_certification',assessment:'not_supported',scope:'资料齐全也不能签发。',next_step:'另行专业复核。',source_module:'backend/engineering.py',source_hash:'a'.repeat(64)},{title:'梁分析',assessment:'supported_with_limits',scope:'限定线弹性。',next_step:'参数需来源。'}]});
 assert.ok(html.includes('应用不支持')&&html.includes('支持有限辅助'));
 assert.ok(html.includes('不代表本项目输入充分')&&html.includes('资料齐全也不能签发'));
 assert.ok(html.includes('<details><summary>查看版本依据'));
 assert.equal(capabilityMarkup({capability_assessments:[]}), '');
});
test('source descriptions and scope are escaped',()=>{
 const html=capabilityMarkup({capability_assessments:[{title:'<img onerror=alert(1)>',assessment:'not_supported',scope:'<script>x</script>',next_step:'<svg>',source_module:'<iframe>',source_hash:'"<x>'}]});
 assert.ok(!html.includes('<script>')&&!html.includes('<img')&&!html.includes('<iframe>'));
 assert.ok(html.includes('&lt;script&gt;'));
});
