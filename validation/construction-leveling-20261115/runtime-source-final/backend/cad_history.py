"""Bounded CAD history membership; detail freshness is always checked separately."""
from . import core

MAX_CURSOR = 2**53 - 1


def page(cad, project_id, *, limit=20, before=None, snapshot=None):
    for value in (before, snapshot):
        if value is not None and (type(value) is not int or not 0 <= value <= MAX_CURSOR):
            raise core.ValidationError('Invalid history cursor')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise core.ValidationError('CAD history page limit must be 1..20')
    if before is not None and snapshot is None:
        raise core.ValidationError('Continuation requires a history snapshot')
    with cad.store.connect() as con:
        # Snapshot freezes membership/order only. A view below still checks the
        # current source, parser and inspection integrity, never historical truth.
        if snapshot is None:
            snapshot = con.execute("SELECT COALESCE(MAX(rowid),0) FROM records WHERE kind='cad' AND project_id=?", (project_id,)).fetchone()[0]
        rows = con.execute("""SELECT r.rowid,r.id FROM records r
            WHERE r.kind='cad' AND r.project_id=? AND r.rowid<=?
              AND (? IS NULL OR r.rowid<?)
              AND r.revision=(SELECT MAX(x.revision) FROM records x
                WHERE x.kind=r.kind AND x.id=r.id AND x.rowid<=?)
            ORDER BY r.rowid DESC LIMIT ?""",
            (project_id, snapshot, before, before, snapshot, limit+1)).fetchall()
    selected = rows[:limit]
    return {'records': [cad.view(project_id, row['id']) for row in selected],
            'snapshot': snapshot, 'next_before': selected[-1]['rowid'] if len(rows)>limit else None,
            'limit': limit, 'membership': 'snapshot_order_current_source_validation'}
