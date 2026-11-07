"""Bounded navigation metadata, never an engineering-result validity claim."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time

from . import core

MAX_ROWID = 2**63 - 1
PAGE_SQL = """
WITH page AS MATERIALIZED (
 SELECT r.rowid AS position, r.id, r.revision
 FROM records r
 WHERE r.kind=? AND r.project_id=? AND r.rowid<=? AND r.rowid<?
 AND r.revision=(
   SELECT MAX(x.revision) FROM records x
   WHERE x.kind=r.kind AND x.id=r.id AND x.rowid<=?
 )
 ORDER BY r.rowid DESC LIMIT ?
)
SELECT p.position, p.id, p.revision,
 json_extract(r.body, '$.project_id') AS bound_project,
 json_extract(r.body, '$.source.file_id') AS file_id,
 substr(json_extract(r.body, '$.source.name'),1,256) AS name,
 json_extract(r.body, '$.source.hash') AS source_hash,
 json_extract(r.body, '$.hash') AS record_hash,
 substr(json_extract(r.body, '$.created_at'),1,64) AS created_at,
 substr(json_extract(r.body, '$.result.format'),1,16) AS format
FROM page p JOIN records r ON r.rowid=p.position
ORDER BY p.position DESC
"""


class CadCatalog:
    ttl_seconds = 1800

    def __init__(self, store):
        self.store = store
        # Navigation cursors expire on service restart; no credentials in cursor.
        self._key = secrets.token_bytes(32)

    def _encode(self, value):
        raw = json.dumps(value, separators=(',', ':'), sort_keys=True).encode()
        payload = base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
        signature = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
        return payload+'.'+signature

    def _decode(self, cursor, pid, kind, limit):
        try:
            if not isinstance(cursor, str) or len(cursor) > 1024:
                raise ValueError()
            payload, signature = cursor.split('.')
            expected = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            raw = base64.b64decode(payload+'='*(-len(payload) % 4), altchars=b'-_', validate=True)
            value = json.loads(raw)
            if set(value) != {'v', 'project', 'kind', 'limit', 'upper', 'before', 'expires'}:
                raise ValueError()
            if value['v'] != 1 or (value['project'], value['kind'], value['limit']) != (pid, kind, limit):
                raise ValueError()
            if any(type(value[k]) is not int for k in ('upper', 'before', 'expires')):
                raise ValueError()
            if not (0 <= value['upper'] < MAX_ROWID and 0 < value['before'] <= value['upper']+1):
                raise ValueError()
            if not time.time() < value['expires'] <= time.time()+self.ttl_seconds+1:
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise core.ValidationError('Catalog cursor invalid or expired; refresh the list') from None

    def page(self, pid, kind, limit=20, cursor=None):
        if kind not in {'cad', 'union'} or type(limit) is not int or not 1 <= limit <= 20:
            raise core.ValidationError('Catalog scope or page size invalid')
        self.store.check_id(pid)
        scope = self._decode(cursor, pid, kind, limit) if cursor else None
        try:
            with self.store.connect() as con:
                con.execute('BEGIN')
                if scope is None:
                    upper = con.execute('SELECT COALESCE(MAX(rowid),0) FROM records WHERE kind=? AND project_id=?',
                                        (kind, pid)).fetchone()[0]
                    # Use <=upper and <before without overflowing signed SQLite rowid.
                    # A MAX_ROWID record has no practical successor: refuse, do not omit.
                    if upper == MAX_ROWID:
                        raise core.ValidationError('Catalog sequence exhausted')
                    scope = {'v': 1, 'project': pid, 'kind': kind, 'limit': limit,
                             'upper': upper, 'before': upper+1, 'expires': int(time.time())+self.ttl_seconds}
                rows = con.execute(PAGE_SQL, (kind, pid, scope['upper'], scope['before'],
                                             scope['upper'], limit+1)).fetchall()
        except sqlite3.Error:
            raise core.ValidationError('Catalog metadata unavailable; no quantities supplied') from None
        items = []
        for row in rows[:limit]:
            if row['bound_project'] != pid or not re.fullmatch(kind+r'_[a-f0-9]{32}', row['id']):
                raise core.ValidationError('Catalog record binding invalid')
            if not isinstance(row['file_id'], str) or not re.fullmatch(r'file_[a-f0-9]{32}', row['file_id']):
                raise core.ValidationError('Catalog source binding invalid')
            if any(not isinstance(row[k], str) or not re.fullmatch(r'[a-f0-9]{64}', row[k])
                   for k in ('source_hash', 'record_hash')):
                raise core.ValidationError('Catalog hash metadata invalid')
            items.append({kind+'_id': row['id'], 'revision': row['revision'],
                          'source': {'file_id': row['file_id'], 'name': str(row['name'] or ''),
                                     'hash': row['source_hash']},
                          'hash': row['record_hash'], 'created_at': row['created_at'],
                          'format': row['format'] if kind == 'cad' else 'IFC',
                          'status': 'unverified', 'result': None,
                          'assessment': 'NAVIGATION_METADATA_REQUIRES_CURRENT_RECORD_CHECK'})
        next_cursor = None
        if len(rows) > limit:
            next_cursor = self._encode({**scope, 'before': rows[limit-1]['position']})
        return {'items': items, 'page_cursor': self._encode(scope), 'next_cursor': next_cursor, 'page_size': limit,
                'has_more': next_cursor is not None, 'snapshot_expires_at': scope['expires'],
                'assessment': 'METADATA_ONLY_NOT_CURRENT_ENGINEERING_RESULTS'}
