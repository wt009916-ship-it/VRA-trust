export function storageDescription(value) {
  const limits = value?.limits;
  if (![value?.project_bytes, value?.project_files].every(x => Number.isSafeInteger(x) && x >= 0) ||
      ![limits?.single_bytes, limits?.project_bytes, limits?.project_files].every(x => Number.isSafeInteger(x) && x > 0) ||
      typeof value.shared_capacity_available !== 'boolean') throw new Error('原件额度数据不完整，请刷新后重试');
  const bytes = n => n < 1048576 ? n.toLocaleString('zh-CN') + ' B' : (n / 1048576).toLocaleString('zh-CN', {maximumFractionDigits: 2}) + ' MiB';
  return `单个文件最大 ${bytes(limits.single_bytes)}。本项目原件 ${bytes(value.project_bytes)} / ${bytes(limits.project_bytes)}，${value.project_files} / ${limits.project_files} 份。` +
    (value.shared_capacity_available ? '' : '本机共享原件容量已满，暂停新增。') + ' 此额度不包括仿真输出等其他存储。';
}

// Cache only within this open form, by the selected File object and fixed project.
// Failed metadata validation should not upload the same original again on retry.
// A lost upload response cannot be deduplicated without a server idempotency key.
export function createEvidenceIntake(projectId, request, post) {
  let savedInput, savedRecord;
  return async (input, fields) => {
    if (input !== savedInput) {
      const form = new FormData(); form.append('file', input);
      const record = await request('/projects/' + projectId + '/files', {method: 'POST', body: form});
      savedInput = input; savedRecord = record;
    }
    return post('/projects/' + projectId + '/evidence', {...fields, name: savedRecord.name, source_file: savedRecord.file_id});
  };
}
