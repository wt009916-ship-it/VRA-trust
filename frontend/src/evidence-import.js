import { request, post } from './api.js';

// Keep both steps bound to the project that opened the import dialog.
export function createEvidenceImporter(projectId) {
  let uploadedFile, record;
  return async (file, details) => {
    if (file !== uploadedFile) {
      const body = new FormData();
      body.append('file', file);
      record = await request('/projects/' + projectId + '/files', { method: 'POST', body });
      uploadedFile = file;
    }
    return post('/projects/' + projectId + '/evidence', {
      ...details, name: record.name, source_file: record.file_id,
    });
  };
}
