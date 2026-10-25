"""Idle-only runtime snapshots and bounded, non-destructive restore drills."""
import json
import shutil
import sqlite3
import threading
import time
import zipfile
from contextlib import contextmanager, closing
from pathlib import Path, PurePosixPath
from . import core
EXCLUDED = {'admin-backups', 'runtime-snapshots', 'restore-drills'}
MAX_FILES, MAX_BYTES = (100000, 20 * 1024 ** 3)

class Operations:

    def __init__(self):
        self.lock = threading.RLock()
        self.active, self.maintenance = (0, False)

    def enter(self):
        with self.lock:
            if self.maintenance:
                return False
            self.active += 1
            return True

    def leave(self):
        with self.lock:
            self.active -= 1

    @contextmanager
    def snapshot(self, store):
        with self.lock:
            if self.maintenance or self.active > 1:
                raise core.ValidationError('其他请求尚未结束，请稍后创建完整备份')
            self.maintenance = True
        try:
            with store.connect() as con:
                busy = con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
                for kind in ('agent', 'import', 'study', 'search'):
                    busy += sum((r.get('status') in {'queued', 'running'} for r in store.list(kind)))
                busy += sum((json.loads(r[0]).get('status') in {'analyzing', 'processing'} for r in con.execute('SELECT body FROM inbox')))
            if busy:
                raise core.ValidationError(f'仍有 {busy} 个活动任务，请等待结束后创建完整备份')
            yield
        finally:
            with self.lock:
                self.maintenance = False

def database_summary(path):
    with closing(sqlite3.connect(path)) as con:
        if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise core.ValidationError('恢复数据库完整性检查失败')
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {table: con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in ('users', 'project_owners', 'records', 'jobs', 'inbox') if table in tables}

def create_snapshot(store, destination):
    root = store.root.resolve()
    entries = []
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDED:
            continue
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise core.ValidationError('运行目录包含链接，拒绝跨目录备份')
        if not path.is_file() or path.name.endswith(('-wal', '-shm')):
            continue
        entries.append((path, relative.as_posix()))
    total = sum((p.stat().st_size for p, _ in entries))
    if len(entries) > MAX_FILES or total > MAX_BYTES:
        raise core.ValidationError('运行目录超过本地备份上限，请使用离线运维流程')
    if shutil.disk_usage(root).free < total * 2 + 64 * 1024 ** 2:
        raise core.ValidationError('磁盘空间不足，无法安全创建备份')
    manifest = {'format': 'vra-runtime-1', 'created_at': core.now(), 'files': [], 'scope': 'Runtime databases, uploads, evidence, runs, workflow checkpoints and private configuration', 'key_portability': 'Windows DPAPI keys require the original OS account; environment keys are external.', 'database': database_summary(store.db)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix('.sqlite3')
    try:
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
            for original, relative in sorted(entries, key=lambda row: row[1]):
                path = original
                if original.suffix == '.sqlite3':
                    with closing(sqlite3.connect(original)) as source, closing(sqlite3.connect(staging)) as target:
                        source.backup(target)
                        if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                            raise core.ValidationError('SQLite 快照完整性检查失败')
                    path = staging
                manifest['files'].append({'path': relative, 'size': path.stat().st_size, 'sha256': core.sha(path)})
                archive.write(path, 'payload/' + relative)
                if path == staging:
                    staging.unlink()
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        staging.unlink(missing_ok=True)
    return {'format': manifest['format'], 'created_at': manifest['created_at'], 'created_unix': time.time(), 'size_bytes': destination.stat().st_size, 'sha256': core.sha(destination), 'file_count': len(entries), 'payload_bytes': total, 'database': manifest['database'], 'key_portability': manifest['key_portability']}

def restore_snapshot(archive_path, destination):
    """Only a new directory is accepted. Failed extracts remain marked incomplete."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise core.ValidationError('恢复目标必须是不存在的新目录；不会覆盖现有运行数据')
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES + 1 or len({i.filename for i in infos}) != len(infos):
            raise core.ValidationError('备份条目过多或重名')
        if archive.getinfo('manifest.json').file_size > 16 * 1024 ** 2:
            raise core.ValidationError('备份清单过大')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'vra-runtime-1':
            raise core.ValidationError('不支持的备份格式')
        files = manifest['files']
        if len(files) > MAX_FILES or sum((f['size'] for f in files)) > MAX_BYTES:
            raise core.ValidationError('备份展开超过上限')
        names = {'payload/' + f['path'] for f in files}
        if len(names) != len(files) or names | {'manifest.json'} != {i.filename for i in infos}:
            raise core.ValidationError('备份内容与清单不一致')
        for entry in files:
            name = entry['path']
            parts = PurePosixPath(name).parts
            if not parts or PurePosixPath(name).is_absolute() or any((p in {'..', '.'} for p in parts)) or any((':' in p or '\\' in p for p in parts)) or (entry['size'] < 0) or (archive.getinfo('payload/' + name).file_size != entry['size']):
                raise core.ValidationError('备份包含非法路径或大小')
        if 'payload/vra.sqlite3' not in names:
            raise core.ValidationError('备份缺少主数据库')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination.parent).free < sum((f['size'] for f in files)) + 64 * 1024 ** 2:
            raise core.ValidationError('恢复磁盘空间不足')
        destination.mkdir()
        marker = destination / '.restore-incomplete'
        marker.write_text('Restore not yet verified', encoding='utf-8')
        for entry in files:
            target = destination.joinpath(*PurePosixPath(entry['path']).parts)
            if not target.resolve().is_relative_to(destination):
                raise core.ValidationError('恢复路径越界')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open('payload/' + entry['path']) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if core.sha(target) != entry['sha256']:
                raise core.ValidationError('恢复文件哈希不一致：' + entry['path'])
        for entry in files:
            if entry['path'].endswith('.sqlite3'):
                database_summary(destination / entry['path'])
        summary = database_summary(destination / 'vra.sqlite3')
        if summary != manifest['database']:
            raise core.ValidationError('恢复记录数量与快照不一致')
        with closing(sqlite3.connect(destination / 'vra.sqlite3')) as con:
            rows = con.execute("SELECT body FROM records r WHERE kind='file' AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)")
            checked = 0
            for row in rows:
                item = json.loads(row[0])
                path = core.relative_file(destination, item['path'])
                if not path.is_file() or core.sha(path) != item['hash']:
                    raise core.ValidationError('数据库引用的上传文件缺失或变更')
                checked += 1
        marker.unlink()
        return {'passed': True, 'file_count': len(files), 'uploaded_files_checked': checked, 'database': summary, 'checked_at': core.now(), 'mode': 'isolated_restore', 'limitations': [manifest['key_portability'], '此校验不代表异机密钥可用或建筑计算已校准。']}
