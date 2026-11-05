import test from 'node:test';
import assert from 'node:assert/strict';
import {storageDescription, createEvidenceIntake} from '../src/storage-intake.js';

test('quota text uses server limits and does not invent missing usage', () => {
  const value = {project_bytes: 1048576, project_files: 4, limits: {single_bytes: 3*1048576, project_bytes: 8*1048576, project_files: 10}, shared_capacity_available: false};
  const text = storageDescription(value);
  assert.ok(text.includes('3 MiB') && text.includes('1 MiB / 8 MiB') && text.includes('4 / 10'));
  assert.ok(storageDescription({...value,project_bytes:19}).includes('19 B'));
  assert.ok(text.includes('暂停新增') && text.includes('不包括仿真输出'));
  assert.throws(() => storageDescription({...value, project_bytes: null}));
  assert.throws(() => storageDescription({...value, limits: {...value.limits, single_bytes: NaN}}));
});

test('metadata failure retries same source without consuming more quota; changed file uploads separately', async () => {
  const uploads = [], registrations = [];
  const submit = createEvidenceIntake('project_original', async (path, options) => {
    uploads.push({path, options}); return {file_id: 'file_' + uploads.length, name: 'original.csv'};
  }, async (path, fields) => {
    registrations.push({path, fields});
    if (registrations.length === 1) throw new Error('invalid locator');
    return fields;
  });
  const input = new File(['sample'], 'original.csv');
  await assert.rejects(submit(input, {source_locator: ''}));
  const retry = await submit(input, {source_locator: 'line 1'});
  assert.equal(uploads.length, 1); assert.equal(retry.source_file, 'file_1');
  assert.equal(registrations[1].path, '/projects/project_original/evidence');
  const changed = await submit(new File(['changed'], 'original.csv'), {source_locator: 'line 2'});
  assert.equal(uploads.length, 2); assert.equal(changed.source_file, 'file_2');
});

test('rejected upload never registers evidence or caches a missing source', async () => {
  let uploads = 0, registrations = 0;
  const submit = createEvidenceIntake('project_a', async () => {uploads++; throw new Error('quota');}, async () => registrations++);
  const input = new File(['sample'], 'source.csv');
  await assert.rejects(submit(input, {})); await assert.rejects(submit(input, {}));
  assert.equal(uploads, 2); assert.equal(registrations, 0);
});
