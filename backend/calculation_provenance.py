"""Current provenance diagnostics and atomic dependency checks for six calculators."""
import json
from pathlib import Path

from . import core


def version(calculator_path):
    return core.hash_json({'calculator': core.sha(calculator_path), 'provenance': core.sha(Path(__file__))})


def sources(record):
    return record.get('evidence_snapshot', record.get('source_snapshot', []))


def validity(domain, record, calculator_version):
    """Reasons describe observed changes, never inferred engineering deficiencies."""
    pid = record['project_id']
    reasons, details = [], []
    def add(code, subject, expected=None, current=None):
        reasons.append(subject if code.startswith('evidence_') else subject + ':file' if code == 'source_file_unavailable' else code)
        details.append({'code': code, 'subject_id': subject, 'expected': expected, 'current': current})
    previous = record.get('calculator_version', record.get('calculator_hash'))
    if previous != calculator_version:
        add('calculator_version', 'calculator', previous, calculator_version)
    project = domain.store.get('project', pid)
    if project['revision'] != record['project_revision']:
        add('project_revision', pid, record['project_revision'], project['revision'])
    files = {}
    for key in ('import_source', 'file_snapshot'):
        if record.get(key):
            old = record[key]
            files[old['file_id']] = old
    for old in sources(record):
        eid = old['evidence_id']
        try:
            current = domain.store.get('evidence', eid)
        except KeyError:
            add('evidence_missing', eid, old['revision'])
            continue
        if current['project_id'] != pid:
            add('evidence_project_mismatch', eid, pid, current['project_id'])
        elif current['review_state'] == 'rejected':
            add('evidence_rejected', eid, old['review_state'], 'rejected')
        elif (old['revision'], old['hash']) != (current['revision'], current['hash']):
            add('evidence_revision', eid, {'revision': old['revision'], 'hash': old['hash']},
                {'revision': current['revision'], 'hash': current['hash']})
        if old.get('source_file'):
            files.setdefault(old['source_file'], None)
    for fid, old in sorted(files.items()):
        try:
            current, _ = domain.file_record(pid, fid)
            if old and (old['revision'], old['hash']) != (current['revision'], current['hash']):
                add('source_file_revision', fid, {'revision': old['revision'], 'hash': old['hash']},
                    {'revision': current['revision'], 'hash': current['hash']})
        except (OSError, ValueError, KeyError):
            add('source_file_unavailable', fid)
    return {'stale_reasons': list(dict.fromkeys(reasons)), 'stale_details': details}


def persist(domain, kind, record, expected_bindings=None, *, pre_insert_check=None):
    """Validate captured and approved revisions in the same SQLite write transaction.

    Another connection/process may revise before BEGIN, but cannot revise between
    these checks and INSERT. Physical originals are immutable by API and rehashed
    here and on every read; this is not protection against hostile disk writes.
    """
    pid = record['project_id']
    with domain.store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        def current(entity, ident):
            row = con.execute('SELECT body FROM records WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1',
                              (entity, ident)).fetchone()
            if row is None:
                raise core.ValidationError('Calculation sources changed; submit a new reviewed plan')
            return json.loads(row[0])
        project = current('project', pid)
        expected_projects = [record['project_revision']]
        if expected_bindings is not None:
            expected_projects.append(expected_bindings['project_revision'])
        if any(project['revision'] != rev for rev in expected_projects):
            raise core.ValidationError('Project changed during calculation; submit a new reviewed plan')
        checks = list(sources(record))
        if expected_bindings is not None:
            checks += expected_bindings['sources']
        for old in checks:
            ev = current('evidence', old['evidence_id'])
            if ev['project_id'] != pid or ev['review_state'] == 'rejected' or (ev['revision'], ev['hash']) != (old['revision'], old['hash']):
                raise core.ValidationError('Calculation sources changed; submit a new reviewed plan')
        files = {ev['source_file'] for ev in sources(record) if ev.get('source_file')}
        snapshots = [record[key] for key in ('import_source', 'file_snapshot') if record.get(key)]
        files.update(f['file_id'] for f in snapshots)
        actual_files = []
        for fid in sorted(files):
            f, _ = domain.file_record(pid, fid)
            actual_files.append(f)
            for old in snapshots:
                if old['file_id'] == fid and old != f:
                    raise core.ValidationError('Calculation file changed; import and review again')
        if expected_bindings is not None and core.hash_json(actual_files) != expected_bindings['files_hash']:
            raise core.ValidationError('Calculation files changed; submit a new reviewed plan')
        if pre_insert_check is not None:
            pre_insert_check()
        return domain.store.put_in(con, kind, record)
