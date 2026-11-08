"""Cold local backups. Never overwrite a destination or refresh engineering hashes.

Archives contain account password hashes and project data: keep them private.
Checksums detect corruption, not authorship. Provider credentials are excluded.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from contextlib import closing, contextmanager
from pathlib import Path, PurePosixPath

from . import core
from .runtime_lock import RuntimeLease, safe_path
from .private_storage import private_mkdir, private_open, private_temporary, verify_private

FORMAT = 'vra-cold-backup-1'
MAX_BYTES = 4 * 1024**3
MAX_FILES = 20000
MAX_MANIFEST = 8 * 1024**2
DIRECTORIES = {'files', 'runs', 'searches', 'drawings', 'recovery', 'conversions'}
EXCLUDED = {'private', 'exports', '.vra.lock', 'vra.sqlite3', 'vra.sqlite3-wal', 'vra.sqlite3-shm'}
SCHEMA = '''
CREATE TABLE records (kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
 project_id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id,revision));
CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL,
 body TEXT NOT NULL, error TEXT);
CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
 display_name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
 csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE project_owners (project_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
CREATE TABLE auth_attempts (bucket TEXT NOT NULL, timestamp REAL NOT NULL);
CREATE INDEX auth_attempt_bucket ON auth_attempts(bucket,timestamp);
'''


def name_ok(name):
    if not isinstance(name, str) or not name or len(name) > 230 or any(c in name for c in '\\:*?"<>|'):
        raise ValueError('Unsafe backup path')
    parts = name.split('/')
    if any(not p or p in {'.', '..'} or p.rstrip(' .') != p or any(ord(c) < 32 for c in p)
           or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in parts):
        raise ValueError('Unsafe backup path')
    if PurePosixPath(name).is_absolute():
        raise ValueError('Unsafe backup path')
    if name != 'vra.sqlite3' and parts[0] not in DIRECTORIES:
        raise ValueError('Unexpected backup artifact')
    return name


def database(path, readonly=False):
    path = safe_path(path)
    con = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=2)
    con.execute('PRAGMA trusted_schema=OFF')
    end = time.monotonic() + 30
    con.set_progress_handler(lambda: int(time.monotonic() > end), 10000)
    return con


def schema(con):
    return sorted((t, n, re.sub(r'\s+', '', sql).lower()) for t, n, sql in
                  con.execute('SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL'))


def check_database(con, entries, read_json):
    with closing(sqlite3.connect(':memory:')) as reference:
        reference.executescript(SCHEMA)
        if schema(con) != schema(reference):
            raise ValueError('Unsupported database schema; do not execute archive migrations')
    if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('Database integrity check failed')
    for kind, body in con.execute("SELECT kind,body FROM records WHERE kind IN ('file','drawing')"):
        obj = json.loads(body)
        key = 'path' if kind == 'file' else 'preview_path'
        name = name_ok(obj[key])
        expected = obj['hash'] if kind == 'file' else obj['result']['preview_sha256']
        if name not in entries or entries[name]['sha256'] != expected:
            raise ValueError('Missing or corrupt registered source/preview')
        if kind=='drawing':
            for derivative in obj.get('derivatives',{}).values():
                derivative_name=name_ok(derivative['path'])
                if derivative_name not in entries or entries[derivative_name]['sha256']!=derivative['sha256']:
                    raise ValueError('Missing or corrupt registered drawing derivative')
    for (body,) in con.execute("SELECT body FROM records WHERE kind='cad'"):
        obj = json.loads(body)
        if obj.get('conversion'):
            derivative = obj['derivative']
            name = name_ok(derivative['path'])
            if name not in entries or entries[name]['sha256'] != derivative['sha256']:
                raise ValueError('Missing or corrupt registered DWG derivative')
    for rid, state, body in con.execute('SELECT id,state,body FROM jobs'):
        if not re.fullmatch('run_[a-f0-9]{32}', rid):
            raise ValueError('Invalid archived run identifier')
        if state == 'succeeded' and any('runs/'+rid+'/'+n not in entries for n in ('request.json','result.json','manifest.json','output/eplusout.sql')):
            raise ValueError('Successful run has missing artifacts')
        if state == 'succeeded':
            prefix = 'runs/'+rid+'/'
            manifest, result, request = (read_json(prefix+n) for n in ('manifest.json','result.json','request.json'))
            job = json.loads(body)
            required = {'input/model.idf','input/weather.epw','input/case.json','input/carbon_profile.json',
                        'output/eplusout.sql','output/eplusout.err','request.json','result.json'}
            if (manifest.get('run_id') != rid or result.get('status') != 'succeeded' or manifest.get('status') != 'succeeded'
                or any(result.get(k) != manifest.get(k) for k in ('run_id','case_id','scheme_id'))
                or any(result.get(k) != job.get(k) for k in ('run_id','case_id','scheme_id'))
                or request != job or not required.issubset(manifest.get('artifact_hashes',{}))):
                raise ValueError('Successful run binding/manifest is incomplete')
            for rel, digest in manifest['artifact_hashes'].items():
                name = name_ok(prefix+rel)
                if name not in entries or entries[name]['sha256'] != digest:
                    raise ValueError('Successful run artifact integrity failed')


def json_reader(entries, read_bytes):
    def read(name):
        if name not in entries or entries[name]['bytes'] > MAX_MANIFEST:
            raise ValueError('Missing/oversized structured backup artifact')
        return json.loads(read_bytes(name))
    return read


def inventory(root):
    found, total = {}, 0
    for top in root.iterdir():
        safe_path(top)
        if top.name in EXCLUDED:
            continue
        if top.name not in DIRECTORIES or not top.is_dir():
            raise ValueError('Unknown runtime entry; backup refuses silent omission')
        for directory, dirs, files in os.walk(top, followlinks=False):
            for child in dirs + files:
                safe_path(Path(directory)/child)
            for child in files:
                path = Path(directory)/child
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('Special or hard-linked backup files are not allowed')
                name = name_ok(path.relative_to(root).as_posix())
                total += info.st_size
                if len(found) >= MAX_FILES or total > MAX_BYTES:
                    raise ValueError('Backup exceeds declared file/byte budget')
                found[name] = {'bytes': info.st_size, 'sha256': core.sha(path)}
    return found


def create_backup(source, archive):
    source, archive = safe_path(source), safe_path(archive)
    if not (source/'vra.sqlite3').is_file() or archive.is_relative_to(source):
        raise ValueError('Use an existing data directory and an archive outside it')
    if archive.exists():
        raise ValueError('Backup destination already exists')
    if not archive.parent.is_dir():
        raise ValueError('Backup parent directory must already exist')
    with RuntimeLease(source, 'maintenance'):
        if (source/'.restore-incomplete').exists():
            raise ValueError('Cannot back up an incomplete restore')
        before = inventory(source)
        # Freeze SQL writers; the separate reader's backup API includes committed WAL pages.
        with closing(database(source/'vra.sqlite3')) as guard:
            guard.execute('BEGIN IMMEDIATE')
            with private_temporary(archive.parent) as tmp:
                snapshot = Path(tmp)/'vra.sqlite3'
                with closing(database(source/'vra.sqlite3', True)) as src, closing(sqlite3.connect(snapshot)) as dst:
                    deadline = time.monotonic() + 30
                    def progress(*_):
                        if time.monotonic() > deadline:
                            raise ValueError('SQLite backup exceeded 30 second budget')
                    src.backup(dst, pages=256, progress=progress, sleep=.05)
                    check_database(dst, before, json_reader(before, lambda name: (source/name).read_bytes()))
                before['vra.sqlite3'] = {'bytes': snapshot.stat().st_size, 'sha256': core.sha(snapshot)}
                if sum(x['bytes'] for x in before.values()) > MAX_BYTES or len(before) > MAX_FILES:
                    raise ValueError('Backup exceeds declared file/byte budget')
                manifest = {'format': FORMAT, 'created_at': core.now(), 'files': before,
                            'excluded': ['private/provider credentials', 'exports/regenerable', 'runtime lock/SQLite sidecars'],
                            'confidential': True, 'encrypted': False,
                            'restore_policy': 'new_directory_sessions_revoked_pending_jobs_failed_provider_unconfigured'}
                encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
                if len(encoded) > MAX_MANIFEST:
                    raise ValueError('Backup manifest too large')
                # Exclusive creation. A failure is retained as an invalid archive, never overwritten.
                with private_open(archive) as raw:
                    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_STORED) as package:
                        for name in sorted(before):
                            package.write(snapshot if name == 'vra.sqlite3' else source/name, name)
                        if inventory(source) != {n: x for n, x in before.items() if n != 'vra.sqlite3'}:
                            raise ValueError('Source files changed during backup')
                        package.writestr('manifest.json', encoded)
                    raw.flush()
                    os.fsync(raw.fileno())
            guard.rollback()
    digest = core.sha(archive)
    verify_backup(archive, digest)
    return {'archive_sha256': digest, 'files': len(before), 'bytes': sum(x['bytes'] for x in before.values()),
            'format': FORMAT, 'encrypted': False, 'provider_credentials_included': False}


def _manifest(package):
    items = package.infolist()
    if len(items) > MAX_FILES + 1:
        raise ValueError('Too many backup entries')
    names = [i.filename for i in items]
    if len({n.casefold() for n in names}) != len(names) or 'manifest.json' not in names:
        raise ValueError('Duplicate entries or missing manifest')
    total = 0
    for item in items:
        if item.filename != 'manifest.json':
            name_ok(item.filename)
        mode = item.external_attr >> 16
        if item.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or item.flag_bits & 1:
            raise ValueError('Special/encrypted archive members are not accepted')
        if item.compress_type != zipfile.ZIP_STORED or item.file_size != item.compress_size:
            raise ValueError('Compressed archives are not accepted; use the application backup format')
        total += item.file_size
    if total > MAX_BYTES + MAX_MANIFEST or package.getinfo('manifest.json').file_size > MAX_MANIFEST:
        raise ValueError('Backup size budget exceeded')
    def unique_pairs(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError('Duplicate JSON manifest keys')
        return value
    manifest = json.loads(package.read('manifest.json'), object_pairs_hook=unique_pairs)
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported backup manifest')
    entries = manifest['files']
    if set(entries) != set(names) - {'manifest.json'} or 'vra.sqlite3' not in entries:
        raise ValueError('Manifest/artifact inventory mismatch')
    for name, item in entries.items():
        name_ok(name)
        if not isinstance(item, dict) or type(item.get('bytes')) is not int or item['bytes'] < 0 or item['bytes'] != package.getinfo(name).file_size or not re.fullmatch('[a-f0-9]{64}', str(item.get('sha256'))):
            raise ValueError('Invalid backup manifest entry')
    if sum(x['bytes'] for x in entries.values()) > MAX_BYTES:
        raise ValueError('Backup size budget exceeded')
    return manifest


def _copy_verified(package, entries, target=None):
    for name, meta in entries.items():
        digest, size = hashlib.sha256(), 0
        with package.open(name) as stream:
            output = None
            try:
                if target:
                    path = safe_path(target/name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    output = private_open(path)
                while chunk := stream.read(1024*1024):
                    size += len(chunk)
                    if size > meta['bytes']:
                        raise ValueError('Backup member exceeds declared size')
                    digest.update(chunk)
                    if output:
                        output.write(chunk)
            finally:
                if output:
                    output.flush()
                    os.fsync(output.fileno())
                    output.close()
        if size != meta['bytes'] or digest.hexdigest() != meta['sha256']:
            raise ValueError('Backup checksum mismatch')


def _check_archive(stream, expected_sha256):
    if os.fstat(stream.fileno()).st_size > MAX_BYTES + MAX_MANIFEST + 10*1024**2:
        raise ValueError('Archive hash/size mismatch')
    position = stream.tell()
    stream.seek(0)
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    stream.seek(position)
    if digest != expected_sha256:
        raise ValueError('Archive hash/size mismatch')


@contextmanager
def _open_backup(archive, expected_sha256):
    archive = safe_path(archive)
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise ValueError('A previously recorded archive SHA-256 is required')
    # Hash and parse the SAME open file; a path replacement cannot substitute another archive.
    with archive.open('rb') as stream:
        _check_archive(stream, expected_sha256)
        with zipfile.ZipFile(stream) as package:
            yield package


def verify_backup(archive, expected_sha256):
    with _open_backup(archive, expected_sha256) as package:
        manifest = _manifest(package)
        _copy_verified(package, manifest['files'])
        with private_temporary(Path(tempfile.gettempdir())) as tmp:
            path = Path(tmp)/'vra.sqlite3'
            with package.open('vra.sqlite3') as src, private_open(path) as dst:
                shutil.copyfileobj(src, dst, length=1024*1024)
            with closing(database(path, True)) as con:
                check_database(con, manifest['files'], json_reader(manifest['files'], package.read))
        _check_archive(package.fp, expected_sha256)
    return {'format': FORMAT, 'archive_sha256': expected_sha256, 'files': len(manifest['files']), 'checksums_valid': True,
            'database_semantics_checked': True}


def restore_backup(archive, target, expected_sha256, *, authenticated_envelope=None):
    if authenticated_envelope is not None and not re.fullmatch('[a-f0-9]{64}',str(authenticated_envelope)):
        raise ValueError('Invalid authenticated envelope identity')
    archive, target = safe_path(archive), safe_path(target)
    if target.exists() or not target.parent.is_dir() or archive.is_relative_to(target):
        raise ValueError('Restore requires a NEW destination under an existing parent; no overwrite')
    with _open_backup(archive, expected_sha256) as package:
        manifest = _manifest(package)
        private_mkdir(target)  # restricted ACL/mode BEFORE plaintext, never overwrite
        marker = target/'.restore-incomplete'
        marker.write_text('Not available for application startup; restore incomplete.\n', encoding='utf-8')
        with RuntimeLease(target, 'maintenance'):
            _copy_verified(package, manifest['files'], target)
            _check_archive(package.fp, expected_sha256)
            with closing(database(target/'vra.sqlite3')) as con:
                check_database(con, manifest['files'], json_reader(manifest['files'], lambda name: (target/name).read_bytes()))
                sessions = con.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
                interrupted = con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
                with con:
                    con.execute('DELETE FROM sessions')
                    con.execute('DELETE FROM auth_attempts')
                    con.execute("UPDATE jobs SET state='failed',error='Restored pending task; create a new run explicitly' WHERE state IN ('queued','running')")
                    revised = []
                    for kind, key, revision, project_id, body in con.execute("SELECT kind,id,revision,project_id,body FROM records r WHERE kind IN ('agent','search') AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)").fetchall():
                        obj = json.loads(body)
                        if obj.get('status') in {'queued', 'running'}:
                            obj.update(status='failed', error='Restored pending task; retry explicitly', revision=revision+1)
                            con.execute('INSERT INTO records VALUES (?,?,?,?,?)', (kind, key, revision+1, project_id, json.dumps(obj, ensure_ascii=False, allow_nan=False)))
                            revised.append({'kind': kind, 'id': key, 'revision': revision+1})
                if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('Restored database integrity failed')
                con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            receipt = {'format': FORMAT, 'restored_at': core.now(), 'archive_sha256': expected_sha256,
                       'files_verified': len(manifest['files']), 'revoked_sessions': sessions,
                       'pending_jobs_failed': interrupted, 'appended_revisions': revised,
                       'provider_credentials_restored': False, 'historical_engineering_hashes_rewritten': False}
            receipt['storage_protection']=verify_private(target,True)
            if authenticated_envelope:
                receipt.update(encrypted_archive_sha256=authenticated_envelope,encrypted=True,authenticated=True)
            core.write_json(target/'recovery'/('restore_'+uuid.uuid4().hex+'.json'), receipt)
            marker.unlink()  # publish only after every check and explicit recovery transform
    return receipt
