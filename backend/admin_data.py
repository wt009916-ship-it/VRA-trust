"""Bounded, administrator-only database explorer and verified SQLite snapshots."""
import json
import sqlite3
import time
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import core

RECORDS = {'projects': ('project', '项目'), 'files': ('file', '资料文件'),
           'evidence': ('evidence', '证据'), 'models': ('model', '建筑模型'),
           'materials': ('material', '材料'), 'imports': ('import', '识别任务'),
           'studies': ('study', '决策研究'), 'searches': ('search', '反例搜索')}
SPECIAL = {'users': '账号', 'ownership': '项目归属', 'jobs': '仿真任务', 'audit': '操作审计', 'sessions': '登录会话', 'tokens': 'API 令牌', 'inbox': '资料收件箱'}
HIDDEN = {'password', 'password_hash', 'salt', 'token', 'token_hash', 'csrf', 'api_key',
          'authorization', 'current_password', 'new_password', 'secret', 'key', 'path'}


def redacted(value):
    if isinstance(value, dict):
        return {k: redacted(v) for k, v in value.items() if k.lower() not in HIDDEN}
    if isinstance(value, list):
        return [redacted(v) for v in value]
    return value


def source(collection):
    """All SQL identifiers are internal constants. Filter values are bound."""
    if collection in RECORDS:
        kind = RECORDS[collection][0]
        return ("SELECT r.id,r.project_id,r.revision,r.body FROM records r WHERE r.kind='"+kind+
                "' AND r.revision=(SELECT MAX(x.revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)")
    if collection == 'users':
        return 'SELECT id,username AS name,display_name,disabled FROM users'
    if collection == 'jobs':
        return 'SELECT id,project_id,state AS status,error FROM jobs'
    if collection == 'ownership':
        return 'SELECT project_id AS id,project_id,user_id FROM project_owners'
    if collection == 'audit':
        return 'SELECT id,actor,action AS name,target,timestamp FROM admin_audit'
    if collection == 'sessions':
        return 'SELECT user_id AS id,user_id,expires FROM sessions'
    if collection == 'tokens':
        return 'SELECT id,user_id,project_id,name,scopes,expires,revoked FROM api_tokens'
    if collection == 'inbox':
        return 'SELECT id,owner,body FROM inbox'
    raise HTTPException(404, '数据集合不存在')


def normalize(row):
    row = dict(row)
    body = json.loads(row.pop('body')) if 'body' in row else {}
    return redacted({**body, **row})


def register_database(app, domain, require, confirm, audit, confirm_type):
    store = domain.store
    backup_root = store.root/'admin-backups'

    @app.get('/api/admin/database')
    def overview(request: Request):
        require(request)
        with store.connect() as con:
            collections = [{'id': key, 'label': label,
                            'count': con.execute('SELECT COUNT(*) FROM ('+source(key)+')').fetchone()[0]}
                           for key, label in {**{k: v[1] for k, v in RECORDS.items()}, **SPECIAL}.items()]
            return {'engine': 'SQLite', 'journal_mode': con.execute('PRAGMA journal_mode').fetchone()[0],
                    'size_bytes': store.db.stat().st_size, 'schema_version': con.execute('PRAGMA user_version').fetchone()[0],
                    'collections': collections, 'record_revisions': con.execute('SELECT COUNT(*) FROM records').fetchone()[0],
                    'file_scope': '数据库备份包含账号及业务索引；上传原文件和模型服务密钥须另行备份。'}

    @app.get('/api/admin/database/collections/{collection}')
    def browse(collection: str, request: Request, q: str = Query(default='', max_length=120),
               page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100)):
        require(request)
        sql = source(collection)
        # Search a sanitized projection, rather than passwords or token hashes.
        with store.connect() as con:
            if collection in RECORDS or collection == 'inbox':
                expression = "COALESCE(json_extract(body,'$.name'),'') || id || COALESCE(json_extract(body,'$.status'),'')"
            else:
                expression = ' || '.join('COALESCE(CAST('+c+' AS TEXT),\'\')' for c in {
                    'users': ['id', 'name', 'display_name'], 'jobs': ['id', 'project_id', 'status', 'error'],
                    'audit': ['id', 'name', 'actor', 'target'], 'sessions': ['user_id'],
                    'tokens': ['id', 'name', 'project_id', 'user_id'], 'ownership': ['project_id', 'user_id']}[collection])
            where, args = (' WHERE LOWER('+expression+') LIKE ? ESCAPE \'\\\'', ['%'+q.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')+'%']) if q else ('', [])
            query = 'SELECT * FROM ('+sql+')'+where
            total = con.execute('SELECT COUNT(*) FROM ('+query+')', args).fetchone()[0]
            rows = con.execute(query+' ORDER BY id DESC LIMIT ? OFFSET ?', [*args, page_size, (page-1)*page_size]).fetchall()
            items = []
            for raw in rows:
                item = normalize(raw)
                if collection in RECORDS or collection == 'inbox':
                    # Full evidence/model structures are fetched only on demand.
                    item = {k: item[k] for k in ('id', 'name', 'project_id', 'revision', 'status', 'review_state', 'updated_at', 'owner', 'created_at') if k in item}
                items.append(item)
            return {'collection': collection, 'items': items, 'total': total, 'page': page, 'page_size': page_size}

    @app.get('/api/admin/database/collections/{collection}/{record_id}')
    def detail(collection: str, record_id: str, request: Request):
        require(request)
        if collection not in RECORDS:
            raise HTTPException(404, '该集合仅提供脱敏列表')
        history = store.history(RECORDS[collection][0], record_id)
        if not history:
            raise HTTPException(404, '记录不存在')
        return {'collection': collection, 'history': redacted(history)}

    @app.post('/api/admin/database/check')
    def check(request: Request):
        actor = require(request)
        with store.connect() as con:
            result = [r[0] for r in con.execute('PRAGMA quick_check')]
            audit(con, actor, 'database_integrity_checked', 'database')
        return {'passed': result == ['ok'], 'results': result, 'checked_at': core.now()}

    @app.get('/api/admin/database/backups')
    def backups(request: Request):
        require(request)
        return sorted((core.read_json(p) for p in backup_root.glob('backup_*.json')), key=lambda r: r['created_unix'], reverse=True)[:100]

    @app.post('/api/admin/database/backups', status_code=201)
    def create_backup(body: confirm_type, request: Request):
        actor = confirm(request, body)
        identifier = 'backup_'+uuid.uuid4().hex
        backup_root.mkdir(exist_ok=True)
        destination = backup_root/(identifier+'.sqlite3')
        try:
            with store.connect() as con, sqlite3.connect(destination) as target:
                con.backup(target)
                if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise core.ValidationError('备份完整性检查失败')
            meta = {'id': identifier, 'created_at': core.now(), 'created_unix': time.time(),
                    'size_bytes': destination.stat().st_size, 'sha256': core.sha(destination), 'integrity': 'ok',
                    'scope': 'SQLite database only; uploaded files and provider secrets excluded'}
            core.write_json(backup_root/(identifier+'.json'), meta)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        with store.connect() as con:
            audit(con, actor, 'database_backup_created', identifier)
        return meta

    @app.get('/api/admin/database/backups/{backup_id}/download')
    def download(backup_id: str, request: Request):
        actor = require(request)
        store.check_id(backup_id)
        if not backup_id.startswith('backup_'):
            raise HTTPException(404, '备份不存在')
        meta_path = backup_root/(backup_id+'.json')
        if not meta_path.is_file():
            raise HTTPException(404, '备份不存在')
        meta = core.read_json(meta_path)
        file = backup_root/(backup_id+'.sqlite3')
        if not file.is_file() or core.sha(file) != meta['sha256']:
            raise core.ValidationError('备份文件校验失败')
        with store.connect() as con:
            audit(con, actor, 'database_backup_downloaded', backup_id)
        return FileResponse(file, filename='vra-'+backup_id+'.sqlite3', media_type='application/vnd.sqlite3')
