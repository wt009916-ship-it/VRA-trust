"""Bounded original-file intake, serialized with its append-only DB records.

This is NOT an OS disk quota: runs, previews, SQLite, multipart temp and backups
are outside this budget. Local administrators and external writers are trusted.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import core
from .private_storage import private_open
from .runtime_lock import safe_path

MIB = 1024**2
SCAN_LIMIT = 50000
EXTENSIONS = {'.idf', '.epw', '.pdf', '.csv', '.xlsx', '.xls', '.png', '.jpg', '.jpeg', '.ifc', '.dxf', '.json', '.xml'}


class StorageError(core.ValidationError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class Limits:
    single_bytes: int = 20*MIB
    project_bytes: int = 256*MIB
    total_bytes: int = 1024*MIB
    project_files: int = 1000
    total_files: int = 10000
    reserve_bytes: int = 256*MIB

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValueError('Storage limits must be positive integers')
        if self.single_bytes > 256*MIB or max(self.project_files, self.total_files) > 20000:
            raise ValueError('Single upload maximum is 256 MiB; file-count maximum is 20000')

    @classmethod
    def from_env(cls):
        mapping = {'single_bytes':('VRA_MAX_UPLOAD_MB',MIB), 'project_bytes':('VRA_SOURCE_PROJECT_MB',MIB),
                   'total_bytes':('VRA_SOURCE_TOTAL_MB',MIB), 'project_files':('VRA_SOURCE_PROJECT_FILES',1),
                   'total_files':('VRA_SOURCE_TOTAL_FILES',1), 'reserve_bytes':('VRA_STORAGE_RESERVE_MB',MIB)}
        values = {}
        for key,(name,scale) in mapping.items():
            if name in os.environ:
                value = os.environ[name]
                if not re.fullmatch('[1-9][0-9]{0,8}',value):
                    raise ValueError(name+' must be a positive integer (no unlimited mode)')
                values[key] = int(value)*scale
        return cls(**values)


class OriginalStorage:
    def __init__(self, store, limits=None):
        self.store = store
        self.limits = limits or Limits.from_env()

    def _inventory(self, con, project_id):
        """Count physical originals, including crash orphans; never auto-delete."""
        try:folder = safe_path(self.store.root/'files')
        except ValueError:
            raise StorageError('storage_integrity','原件目录路径不安全，请检查存储') from None
        physical = {}
        if folder.exists():
            with os.scandir(folder) as entries:
                for entry in entries:
                    if len(physical) >= SCAN_LIMIT:
                        raise StorageError('storage_scan_limit','原件目录超过检查预算，请由管理员检查；没有删除文件')
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0) & 0x400:
                        raise StorageError('storage_integrity','原件目录含非普通文件或链接，请检查存储')
                    physical['files/'+entry.name] = info.st_size
        count = size = 0
        seen = set()
        rows = con.execute("SELECT id,project_id,body FROM records r WHERE kind='file' AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)")
        for index,row in enumerate(rows):
            if index >= SCAN_LIMIT:
                raise StorageError('storage_scan_limit','原件记录超过检查预算，请由管理员检查')
            try:
                obj = json.loads(row['body'])
                path = obj['path']
                if (obj['file_id'] != row['id'] or obj['project_id'] != row['project_id']
                    or not isinstance(path,str) or not re.fullmatch(r'files/file_[a-f0-9]{32}\.[a-z]+',path)
                    or Path(path).stem != row['id'] or path in seen
                    or type(obj['size']) is not int or obj['size'] <= 0 or physical.get(path) != obj['size']):
                    raise ValueError()
                seen.add(path)
                if row['project_id'] == project_id:
                    count += 1; size += obj['size']
            except (ValueError,KeyError,TypeError):
                raise StorageError('storage_integrity','已登记原件缺失或大小/身份不一致，请检查存储；旧记录未修改') from None
        return {'project_bytes':size,'project_files':count,'total_bytes':sum(physical.values()),'total_files':len(physical)}

    def _admit(self, usage, sizes):
        limits = self.limits
        if any(n > limits.single_bytes for n in sizes):
            raise StorageError('file_size_limit','单个文件超过上传限额',413)
        for field,added in [('project_bytes',sum(sizes)),('project_files',len(sizes)),('total_bytes',sum(sizes)),('total_files',len(sizes))]:
            if usage[field]+added > getattr(limits,field):
                scope = '本项目' if field.startswith('project') else '本机共享原件存储'
                raise StorageError('source_'+field+'_limit',scope+'已达到累计限额；请联系管理员调整容量，原件与历史不会自动删除',507)
        if shutil.disk_usage(self.store.root).free < limits.reserve_bytes+sum(sizes):
            raise StorageError('storage_reserve','可用磁盘不足以保留安全余量，暂停新增原件',507)

    def usage(self, project_id):
        self.store.get('project',project_id)
        try:
            with self.store.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                used = self._inventory(con,project_id)
                shared = used['total_bytes'] < self.limits.total_bytes and used['total_files'] < self.limits.total_files
                return {'scope':'original_files_only','project_bytes':used['project_bytes'],'project_files':used['project_files'],
                        'limits':{k:getattr(self.limits,k) for k in ('single_bytes','project_bytes','project_files')},
                        'shared_capacity_available':shared,
                        'limitations':['不包含仿真输出、预览、数据库、上传临时目录和备份；不是操作系统磁盘配额。']}
        except (OSError,sqlite3.Error):
            raise StorageError('storage_unavailable','无法检查存储状态，请稍后重试') from None

    @contextmanager
    def import_batch(self, project_id, inputs):
        """Yield one open DB transaction and new file records. Caller may append
        project/ownership/evidence in it, with no nested Store.put/commit calls.
        A crash orphan remains charged globally; a registered file is never deleted.
        """
        self.store.check_id(project_id)
        if not inputs or len(inputs) > self.limits.project_files:
            raise StorageError('source_project_files_limit','导入文件数量超出项目限额',507)
        drafts = []
        for filename,content in inputs:
            extension = Path(filename).suffix.lower()
            if extension not in EXTENSIONS:raise core.ValidationError('Unsupported file extension')
            if not isinstance(content,bytes) or not content:raise core.ValidationError('Empty or invalid file')
            if len(content)>self.limits.single_bytes:raise StorageError('file_size_limit','单个文件超过上传限额',413)
            fid = 'file_'+uuid.uuid4().hex
            record = {'file_id':fid,'project_id':project_id,'name':Path(filename.replace('\\','/')).name,
                      'path':'files/'+fid+extension,'hash':hashlib.sha256(content).hexdigest(),'size':len(content),'timestamp':core.now()}
            drafts.append((record,content))
        created = []
        con = self.store.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            self._admit(self._inventory(con,project_id),[len(content) for _,content in drafts])
            folder = safe_path(self.store.root/'files');folder.mkdir(exist_ok=True)
            records = []
            for record,content in drafts:
                path = safe_path(self.store.root/record['path'])
                with private_open(path) as stream:
                    info = os.fstat(stream.fileno())
                    created.append((record['file_id'],path,info.st_dev,info.st_ino))
                    stream.write(content);stream.flush();os.fsync(stream.fileno())
                records.append(self.store.put_in(con,'file',record))
            yield con,records
            con.commit()
        except BaseException:
            try:con.rollback()
            finally:con.close()
            # A failed commit can have an uncertain outcome. Re-read committed
            # records first; if readback fails, preserve all files conservatively.
            try:
                with self.store.connect() as check:
                    retained = {fid for fid,_,_,_ in created if check.execute("SELECT 1 FROM records WHERE kind='file' AND id=?",(fid,)).fetchone()}
                for fid,path,dev,ino in created:
                    if fid not in retained:
                        safe_path(path)
                        info = path.stat()
                        if (info.st_dev,info.st_ino)==(dev,ino):path.unlink()
            except (OSError,ValueError,sqlite3.Error):
                pass  # crash/cleanup remnants remain visible to the next inventory
            raise
        finally:con.close()
