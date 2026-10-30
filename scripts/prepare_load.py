"""Create a fresh isolated load fixture from an existing public-reference model.

Never copies accounts, credentials, project ownership, private settings or runs.
Session material is written outside the checkout and must not be published.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-runtime', type=Path, required=True)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--users', type=int, default=20, choices=range(1, 101))
    parser.add_argument('--public-source-url', required=True)
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    source, output = args.source_runtime.resolve(), args.out_dir.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output.exists() or output == checkout or checkout in output.parents or source == output or source in output.parents:
        parser.error('Output must be a new isolated directory outside source and checkout')
    output.mkdir(parents=True)
    runtime = output/'runtime'
    os.environ['VRA_DATA_DIR'] = str(runtime)
    os.environ['VRA_REGISTRATION_MODE'] = 'open'
    from backend.auth import Auth, Registration
    from backend.identity_security import MFA, seal
    from backend.model_schema import ModelDraft
    from backend.store import Store
    store = Store(runtime)
    auth = Auth(store)
    MFA(auth)
    # Read-only consistent snapshot; no source state changes.
    with sqlite3.connect(source.joinpath('vra.sqlite3').as_uri()+'?mode=ro', uri=True) as con:
        rows = [json.loads(r[0]) for r in con.execute("SELECT body FROM records r WHERE project_id=? AND kind IN ('project','model','file') AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)", (args.project_id,))]
    models = [r for r in rows if 'model_id' in r]
    if not models:
        parser.error('Source project must have a real saved model')
    files = [r for r in rows if 'file_id' in r]
    if not args.public_source_url.startswith('https://') or not any(r['hash'] == args.source_sha256 for r in files):
        parser.error('Provide a public source URL and the matching original-file SHA256')
    for row in files:
        src = (source/row['path']).resolve()
        if source not in src.parents:
            parser.error('Source file escapes runtime')
        if hashlib.sha256(src.read_bytes()).hexdigest() != row['hash']:
            parser.error('Source-file hash mismatch')
        dst = runtime/row['path']
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    sessions = []
    for index in range(args.users):
        _, user = auth.register(Registration(username=f'load_engineer_{index:03}', display_name='Isolated load fixture', password='Load-'+secrets.token_urlsafe(24)))
        mapping = {args.project_id: 'project_'+uuid.uuid4().hex}
        mapping.update({r['file_id']: 'file_'+uuid.uuid4().hex for r in files})
        mapping.update({r['model_id']: 'model_'+uuid.uuid4().hex for r in models})
        for row in rows:
            text = json.dumps(row)
            for old, new in mapping.items(): text = text.replace(old, new)
            cloned = json.loads(text)
            # Keep immutable source paths, with new owner-scoped file records.
            if 'file_id' in row: cloned['path'] = row['path']
            cloned['revision'] = 1
            kind = 'model' if 'model_id' in row else 'file' if 'file_id' in row else 'project'
            if kind == 'project':
                cloned['data_nature'] = 'engineering_reference'
            store.put(kind, cloned)
        auth.own(mapping[args.project_id], user['id'])
        if index % 2:
            import pyotp
            with store.connect() as con:
                con.execute('INSERT INTO account_mfa VALUES (?,?,1,-1,NULL,NULL)', (user['id'], seal(pyotp.random_base32())))
        token, session = auth.new_session(user['id'], assurance='pwd+otp' if index % 2 else 'pwd')
        sessions.append({'cookie': token, 'csrf': session['csrf'], 'project_id': mapping[args.project_id]})
    fixture = {'sessions': sessions, 'draft_fields': list(ModelDraft.model_fields),
               'source_project': args.project_id, 'rooms': len(models[0]['rooms']), 'users': args.users,
               'public_source_url': args.public_source_url, 'source_sha256': args.source_sha256}
    (output/'sessions.private.json').write_text(json.dumps(fixture), encoding='utf-8')
    print(json.dumps({k: fixture[k] for k in ('source_project', 'rooms', 'users')}))


if __name__ == '__main__':
    main()
