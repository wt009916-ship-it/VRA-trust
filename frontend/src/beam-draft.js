// One tab, memory only. A draft grants neither project access nor permission to submit.
export function createBeamDraft(clock = Date.now) {
  let saved = null;
  let timer;
  const ttl = 15 * 60 * 1000;
  function discard() { clearTimeout(timer); saved = null; }
  const stamp = evidence => JSON.stringify(evidence.map(e => [e.evidence_id, e.revision, e.hash, e.review_state]).sort((a,b) => a[0].localeCompare(b[0])));
  function current(userId) {
    if (saved && (saved.userId !== userId || clock() >= saved.expires)) discard();
    return saved;
  }
  return {
    capture(userId, project, evidence, input) {
      discard();
      saved = userId && project && input ? {userId, projectId:project.project_id,
        revision:project.revision, sources:stamp(evidence), input:structuredClone(input), expires:clock()+ttl} : null;
      if (saved) { timer = setTimeout(discard, ttl); timer.unref?.(); }
    },
    target(userId) { return current(userId)?.projectId ?? null; },
    take(userId, project, evidence) {
      const draft = current(userId); discard();
      if (!draft || draft.projectId !== project.project_id || draft.revision !== project.revision || draft.sources !== stamp(evidence)) return null;
      return draft.input;
    },
    clear: discard
  };
}
