import test from 'node:test';
import assert from 'node:assert/strict';
import { createPoller } from '../src/polling.js';
import { createEvidenceImporter } from '../src/evidence-import.js';
import { request } from '../src/api.js';

const flush = () => new Promise(resolve => setImmediate(resolve));

test('a transient connection failure retries and returns to normal polling', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0, errors = 0;
  const poller = createPoller(async () => {
    if (++calls === 1) throw new Error('network offline');
  }, { onError: () => errors++ });
  poller.start();
  t.mock.timers.tick(3000); await flush();
  assert.equal(errors, 1);
  t.mock.timers.tick(6000); await flush();
  assert.equal(calls, 2);
  t.mock.timers.tick(3000); await flush();
  assert.equal(calls, 3);
  poller.stop();
  t.mock.timers.tick(60000); await flush();
  assert.equal(calls, 3);
});

test('slow requests cannot overlap and an abandoned project cannot restart polling', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let release, calls = 0, errors = 0;
  const poller = createPoller(() => {
    calls++;
    return new Promise((resolve, reject) => { release = reject; });
  }, { onError: () => errors++ });
  poller.start();
  t.mock.timers.tick(3000); await flush();
  t.mock.timers.tick(60000); await flush();
  assert.equal(calls, 1);
  poller.stop();
  release(new Error('old project disconnected')); await flush();
  t.mock.timers.tick(60000); await flush();
  assert.equal(calls, 1);
  assert.equal(errors, 0);
});

test('an expired session stops retries', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  createPoller(async () => {
    calls++;
    throw Object.assign(new Error('login required'), { status: 401 });
  }).start();
  t.mock.timers.tick(3000); await flush();
  t.mock.timers.tick(60000); await flush();
  assert.equal(calls, 1);
});

test('evidence registration retries reuse the uploaded file and original project', async t => {
  const requests = [];
  let registrations = 0;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, body: options.body });
    if (url.endsWith('/files')) return Response.json({ file_id: 'file_original', name: 'wall.csv' });
    if (++registrations === 1) return Response.json({ detail: 'fix source locator' }, { status: 422 });
    return Response.json({ evidence_id: 'saved' });
  });
  let selectedProject = 'project_original';
  const importEvidence = createEvidenceImporter(selectedProject);
  const file = new File(['wall,0.2'], 'wall.csv');
  await assert.rejects(importEvidence(file, { source_locator: '' }), /fix source locator/);
  selectedProject = 'project_other';
  await importEvidence(file, { source_locator: 'row 1' });
  assert.equal(requests.filter(r => r.url.endsWith('/files')).length, 1);
  assert.ok(requests.every(r => r.url.startsWith('/api/projects/project_original/')));
  assert.equal(JSON.parse(requests.at(-1).body).source_file, 'file_original');
  assert.equal(JSON.parse(requests.at(-1).body).source_locator, 'row 1');
});

test('a legitimate null response stays nullable and malformed success responses fail visibly', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(null));
  assert.equal(await request('/projects/example/geometry'), null);
  globalThis.fetch = async () => new Response('<html>connection error</html>');
  await assert.rejects(request('/projects/example/runs'), /无法读取的数据/);
});
