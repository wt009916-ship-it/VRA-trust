"""Real HTTP acceptance against an isolated benchmark_agent_server.py runtime.

Requires the original Schependomlaan IFC, Golden EPW, and real local llama server.
No expected prose or fake model replies are injected. Never target a user runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ifc', type=Path, required=True)
    parser.add_argument('--epw', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:8770', timeout=180) as client:
        auth = client.post('/api/auth/register', json={'username': 'hardening_'+secrets.token_hex(4),
            'display_name': '隔离验收 · 非正式项目', 'password': secrets.token_urlsafe(24)})
        auth.raise_for_status()
        client.headers['X-CSRF-Token'] = auth.json()['csrf_token']
        # This isolated first account owns these private temporary records only.
        config = client.put('/api/developer/provider', json={'enabled': True, 'model': 'qwen3-benchmark',
            'endpoint': 'http://127.0.0.1:8791/v1/chat/completions'})
        if config.status_code != 403:  # Further isolated accounts reuse the first admin's configuration.
            config.raise_for_status()
        project = client.post('/api/projects', json={'name': '商业打磨验收 · Schependomlaan / Golden',
            'building': {'use': 'office', 'location': 'Test inputs; not a real combined building', 'region': 'TEST', 'area_m2': 1}})
        project.raise_for_status()
        base = '/api/projects/'+project.json()['project_id']
        result = {'scope': 'Product acceptance; IFC and EPW are independent public inputs, not one building',
                  'project_id': project.json()['project_id'], 'health': client.get('/api/health').json()}
        for name, path in [('ifc', args.ifc), ('epw', args.epw)]:
            data = path.read_bytes()
            before = hashlib.sha256(data).hexdigest()
            started = time.monotonic()
            upload = client.post(base+'/files', files={'file': (path.name, data)})
            result[name] = {'sha256': before, 'bytes': len(data), 'upload_status': upload.status_code}
            upload.raise_for_status()
            if name == 'ifc':
                imported = client.post(base+'/imports', json={'file_id': upload.json()['file_id']})
                record = client.get(base+'/imports').json()[0]
                report = client.get(base+'/imports/'+record['import_id']+'/report.json')
                report.raise_for_status()
                save('ifc-diagnostics.json', report.json())
                result[name].update(import_status=imported.status_code, diagnostics=record['diagnostics'],
                                    model=client.get(base+'/model').json())
                assert imported.status_code == 409
                assert (record['diagnostics']['total'], record['diagnostics']['extracted'], record['diagnostics']['blocked']) == (100, 6, 94)
                assert result[name]['model'] is None
            else:
                weather = client.post(base+'/weather/epw', json={'file_id': upload.json()['file_id']})
                weather.raise_for_status()
                result[name]['annual'] = weather.json()['annual']
            result[name]['seconds'] = time.monotonic()-started
            result[name]['source_unchanged'] = before == hashlib.sha256(path.read_bytes()).hexdigest()
        save('acceptance.json', result)
        records = []
        for mode in ['local', 'provider', 'provider']:
            created = client.post(base+'/agent/chat', json={'message': '核对站点、记录数、年均温、HDD18、CDD26、太阳辐射和来源 SHA256，不运行仿真。',
                'mode': mode, 'task': 'weather', 'allow_compute': False})
            created.raise_for_status()
            task = created.json()
            deadline = time.monotonic()+360
            while task['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.5)
                task = client.get(base+'/agent/'+task['agent_id']).json()
            records.append(task)
            save('agent-actual.json', records)
            assert task['status'] in {'succeeded', 'partial'}, task
            fact = task['answer']['weather'][0]
            assert fact['annual'] == result['epw']['annual']
            assert fact['quality']['records'] == 8760 and fact['source_hash'] == result['epw']['sha256']
        assert client.get(base+'/runs').json() == []
        result['tasks'] = [{'mode': t['mode'], 'status': t['status'], 'tool_status': t['tool_status'],
                            'explanation_status': t['explanation_status'], 'verified_weather_matches': True} for t in records]
        result['queued_simulations'] = 0
        save('acceptance.json', result)
        # Short-lived browser session material stays in the isolated output directory.
        save('browser-session.private.json', {'cookies': dict(client.cookies), 'csrf': client.headers['X-CSRF-Token']})
        print(json.dumps({k:v for k,v in result.items() if k not in {'ifc', 'health'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
