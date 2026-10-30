"""Owner-scoped operational overview; current run validity stays with Domain.view."""
import json

from fastapi import Request

from . import core


def register_workspace(app, domain, auth):
    @app.get('/api/workspace')
    def overview(request: Request):
        uid = request.state.user['id']
        with domain.store.connect() as con:
            con.execute('BEGIN')
            projects = [json.loads(r[0]) for r in con.execute("""
                SELECT r.body FROM records r JOIN project_owners o ON o.project_id=r.id
                WHERE o.user_id=? AND r.kind='project' AND r.revision=(
                    SELECT MAX(x.revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)
                ORDER BY r.rowid DESC""", (uid,))]
            evidence = [json.loads(r[0]) for r in con.execute("""
                SELECT r.body FROM records r JOIN project_owners o ON o.project_id=r.project_id
                WHERE o.user_id=? AND r.kind='evidence' AND r.revision=(
                    SELECT MAX(x.revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)""", (uid,))]
            jobs = [dict(r) for r in con.execute("""
                SELECT j.id,j.project_id,j.state,j.body FROM jobs j
                JOIN project_owners o ON o.project_id=j.project_id WHERE o.user_id=? ORDER BY j.rowid DESC""", (uid,))]
            batches = [json.loads(r[0]) for r in con.execute(
                "SELECT body FROM inbox WHERE owner=? ORDER BY rowid DESC", (uid,))]
        by_project, runs = {}, {}
        for ev in evidence:
            by_project.setdefault(ev['project_id'], []).append(ev)
        for job in jobs:
            runs.setdefault(job['project_id'], []).append(job)
        cards, activity = [], []
        for project in projects:
            pid = project['project_id']
            sources, history = by_project.get(pid, []), runs.get(pid, [])
            pending = sum(e['review_state'] == 'pending' for e in sources)
            current = None
            if history:
                try:
                    view = domain.view(history[0]['id'])
                    current = {k: view.get(k) for k in ('run_id', 'scheme_id', 'status', 'created_at', 'error')}
                except (core.ValidationError, KeyError, OSError) as exc:
                    current = {'run_id': history[0]['id'], 'status': 'unavailable', 'error': str(exc)}
            active = sum(j['state'] in {'queued', 'running'} for j in history)
            status = 'running' if active else (current or {}).get('status') or ('review' if pending else 'preparing')
            if active:
                next_action = {'view': 'simulation', 'label': '查看计算任务'}
            elif not sources:
                next_action = {'view': 'intake', 'label': '导入项目资料'}
            elif pending:
                next_action = {'view': 'evidence', 'label': '核对待审资料'}
            elif not any(e['type'] == 'idf' and e['review_state'] != 'rejected' for e in sources):
                next_action = {'view': 'spatial', 'label': '继续建立模型'}
            elif not any(e['type'] == 'epw' and e['review_state'] != 'rejected' for e in sources):
                next_action = {'view': 'weather', 'label': '补充计算天气'}
            else:
                next_action = {'view': 'simulation', 'label': '查看结果与报告' if status == 'succeeded' else '检查并运行仿真'}
            updated = max([project['updated_at']] + [e['timestamp'] for e in sources]
                          + [json.loads(j['body'])['created_at'] for j in history])
            cards.append({'project_id': pid, 'name': project['name'], 'building': project['building'],
                          'data_nature': project['data_nature'], 'revision': project['revision'],
                          'updated_at': updated, 'evidence_count': len(sources), 'pending_count': pending,
                          'run_count': len(history), 'active_count': active, 'status': status,
                          'latest_run': current, 'next_action': next_action})
            activity.append({'project_id': pid, 'project_name': project['name'], 'title': '建立项目',
                             'at': project['created_at'], 'view': 'readiness'})
            for ev in sources:
                activity.append({'project_id': pid, 'project_name': project['name'], 'title': ev['name'],
                                 'detail': {'pending': '资料待复核', 'confirmed': '资料已确认', 'rejected': '资料已拒绝'}[ev['review_state']],
                                 'at': ev['timestamp'], 'view': 'evidence'})
            if current:
                activity.append({'project_id': pid, 'project_name': project['name'], 'title': '最近仿真 · ' + current['status'],
                                 'at': current.get('created_at', updated), 'view': 'simulation'})
        unfinished = [{'id': b['id'], 'project_id': b.get('project_id'), 'status': b['status'],
                       'created_at': b['created_at'], 'file_count': len(b['files']),
                       'names': [f['name'] for f in b['files'][:3]]}
                      for b in batches if b['status'] != 'committed'
                      and (not b.get('project_id') or any(p['project_id'] == b['project_id'] for p in cards))]
        return {'generated_at': core.now(), 'projects': cards, 'intakes': unfinished,
                'activity': sorted(activity, key=lambda x: x['at'], reverse=True)[:12],
                'counts': {'projects': len(cards), 'pending_evidence': sum(p['pending_count'] for p in cards),
                           'active_runs': sum(p['active_count'] for p in cards), 'unfinished_intakes': len(unfinished)}}
