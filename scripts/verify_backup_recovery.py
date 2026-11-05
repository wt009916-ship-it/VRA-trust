"""Actual reference EnergyPlus + CAD/OCR -> cold backup -> authenticated recovery.

Never uses the user's runtime. No credentials or session tokens in evidence.
"""
import io
import argparse
import json
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ezdxf
from fastapi.testclient import TestClient
from backend import core
from backend.api import create_app
from backend.backup import create_backup, restore_backup, verify_backup
from backend.encrypted_backup import create_encrypted, restore_encrypted, verify_encrypted
from backend.private_storage import verify_private


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output');parser.add_argument('--encrypted',action='store_true')
    args=parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    password = secrets.token_urlsafe(32)
    archive_password=secrets.token_urlsafe(48).encode()  # isolated, never persisted or printed
    def create(source,archive):
        return create_encrypted(source,archive,archive_password) if args.encrypted else create_backup(source,archive)
    def verify(archive,digest):
        return verify_encrypted(archive,archive_password,digest) if args.encrypted else verify_backup(archive,digest)
    def restore(archive,target,digest):
        return restore_encrypted(archive,target,archive_password,digest) if args.encrypted else restore_backup(archive,target,digest)
    checks = []
    def check(value, name):
        checks.append({'name': name, 'passed': bool(value)})
        core.write_json(out/'checks.json', checks)
        if not value:
            raise AssertionError(name)
    def login(client):
        response = client.post('/api/auth/login', json={'username':'backup_reference','password':password})
        check(response.status_code == 200, 'restored account login')
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    def upload(client, pid, name, data):
        response = client.post(f'/api/projects/{pid}/files', files={'file':(name,data)})
        check(response.status_code == 201, 'upload '+name)
        return response.json()['file_id']
    with TestClient(create_app(out/'source')) as client:
        response = client.post('/api/auth/register',json={'username':'backup_reference','display_name':'Public reference recovery test','password':password})
        check(response.status_code == 200, 'isolated account')
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        response = client.post('/api/reference-projects')
        check(response.status_code == 201, 'public reference project')
        pid = response.json()['project_id']
        for evidence in client.get(f'/api/projects/{pid}/evidence').json():
            response = client.patch(f"/api/projects/{pid}/evidence/{evidence['evidence_id']}", json={
                'expected_revision':evidence['revision'],'review_state':'confirmed','responsible_person':'Reference-only recovery verification',
                'review_note':'Official 5Zone reference inputs, not a measured building or professional approval.'})
            check(response.status_code == 200, 'reference evidence binding')
        response = client.post('/api/runs', json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'reference_scenario'})
        check(response.status_code == 202, 'submit actual EnergyPlus')
        rid = response.json()['run_id']
        print('Actual reference EnergyPlus submitted', flush=True)
        end = time.monotonic()+180
        while time.monotonic()<end:
            before = client.get(f'/api/runs/{rid}/result').json()
            if before['status'] not in {'running','queued'}:
                break
            time.sleep(.5)
        check(before['status']=='succeeded' and before['engine_calls_executed']==1, 'one real successful engine call')
        report_before = client.get(f'/api/runs/{rid}/report.json').json()
        core.write_json(out/'report-before.json', report_before)
        core.write_json(out/'run-before.json', before)
        # Independent simple CAD input, not a fabricated parser response.
        document = ezdxf.new('R2010');document.units=4
        document.modelspace().add_line((0,0),(3000,4000))
        stream = io.StringIO();document.write(stream)
        fid = upload(client,pid,'independent.dxf',stream.getvalue().encode())
        response = client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid})
        check(response.status_code==201,'actual CAD parser')
        cad = response.json()
        check(cad['result']['objects'][0]['length_m']==5,'independent five metre CAD line')
        fid = upload(client,pid,'independent.png',(ROOT/'fixtures/drawing_gold/clean.png').read_bytes())
        response = client.post(f'/api/projects/{pid}/drawings',json={'file_id':fid})
        check(response.status_code==201,'actual OCR')
        drawing=response.json();base=f"/api/projects/{pid}/drawings/{drawing['drawing_id']}"
        response = client.post(base+'/review',json={'expected_revision':1,'candidate_id':drawing['result']['candidates'][0]['candidate_id'],
              'decision':'confirmed','basis':'Independent synthetic fixture text reviewed for restoration test, no engineering interpretation.'})
        check(response.status_code==200,'review history created')
        history=client.app.state.domain.store.history('drawing',drawing['drawing_id'])
        preview=client.get(base+'/preview.png').content
        token=client.cookies.get('vra_session')
        evidence_before=client.get(f'/api/projects/{pid}/evidence').json()
    hashes_before={p.relative_to(out/'source').as_posix():core.sha(p) for folder in ('files','runs','drawings') for p in (out/'source'/folder).rglob('*') if p.is_file()}
    archive=out/('backup.vraenc' if args.encrypted else 'backup.zip');meta=create(out/'source',archive)
    check(verify(archive,meta['archive_sha256'])['database_semantics_checked'],'archive database and file verification')
    if args.encrypted:
        check(b'password_hash' not in archive.read_bytes() and b'project_id' not in archive.read_bytes(),'encrypted package hides database names and values')
        try:restore_encrypted(archive,out/'wrong-key',secrets.token_urlsafe(48).encode(),meta['archive_sha256'])
        except ValueError:check(not (out/'wrong-key').exists(),'wrong key creates no runtime')
        else:check(False,'wrong key rejected')
        altered=out/'altered.vraenc';raw=bytearray(archive.read_bytes());raw[-1]^=1;altered.write_bytes(raw)
        try:restore_encrypted(altered,out/'altered-runtime',archive_password,core.sha(altered))
        except ValueError:check(not (out/'altered-runtime').exists(),'altered tag creates no runtime')
        else:check(False,'altered tag rejected')
    receipt=restore(archive,out/'restored',meta['archive_sha256'])
    if args.encrypted:check(verify_private(out/'restored',True)['verified'],'restored runtime private permissions verified')
    core.write_json(out/'backup-summary.json',meta);core.write_json(out/'restore-summary.json',receipt)
    check(all(core.sha(out/'restored'/n)==h for n,h in hashes_before.items()),'every original/run/preview byte hash unchanged')
    print('Archive restored; verifying accounts, native artifacts and reports',flush=True)
    with TestClient(create_app(out/'restored')) as client:
        client.cookies.set('vra_session',token)
        check(client.get('/api/projects').status_code==401,'old session cannot replay')
        login(client)
        after=client.get(f'/api/runs/{rid}/result').json()
        check(after==before,'native run API exactly matches before backup')
        report_after = client.get(f'/api/runs/{rid}/report.json').json()
        core.write_json(out/'report-after.json', report_after)
        check({k:v for k,v in report_after.items() if k!='generated_at'}=={k:v for k,v in report_before.items() if k!='generated_at'},
              'same report content except new export generated_at')
        pdf=client.get(f'/api/runs/{rid}/report.pdf')
        check(pdf.status_code==200 and pdf.content.startswith(b'%PDF'),'actual restored PDF generation')
        (out/'restored-report.pdf').write_bytes(pdf.content)
        check(client.get(f"/api/projects/{pid}/cad-inspections/{cad['cad_id']}").json()==cad,'CAD result unchanged')
        check(client.get(base+'/preview.png').content==preview,'OCR preview unchanged')
        check(client.app.state.domain.store.history('drawing',drawing['drawing_id'])==history,'all OCR review revisions unchanged')
        check(client.get(f'/api/projects/{pid}/evidence').json()==evidence_before,'evidence history/source declarations unchanged')
        check(not client.get('/api/developer/provider').json()['key_configured'],'provider unconfigured after restore')
        selected=next(e for e in evidence_before if e['type']=='idf' and e['scheme_id']=='baseline')
        response=client.patch(f"/api/projects/{pid}/evidence/{selected['evidence_id']}",json={
            'expected_revision':selected['revision'],'review_state':'rejected','responsible_person':'Reference-only failure injection',
            'review_note':'Deliberately revoke input to verify restored data cannot resurrect stale engineering results.'})
        check(response.status_code==200,'revoke evidence on restored copy only')
        check(client.get(f'/api/runs/{rid}/result').json()['status']=='stale','restored result becomes stale on revoked input')
    second=out/('stale-backup.vraenc' if args.encrypted else 'stale-backup.zip');meta2=create(out/'restored',second)
    restore(second,out/'stale-restored',meta2['archive_sha256'])
    with TestClient(create_app(out/'stale-restored',start_worker=False)) as client:
        login(client)
        stale=client.get(f'/api/runs/{rid}/result').json()
        check(stale['status']=='stale' and stale['metrics'] is None,'second recovery preserves stale refusal')
    check(all(core.sha(out/'source'/n)==h for n,h in hashes_before.items()),'original source artifacts retained unchanged')
    summary={'checks_passed':len(checks),'actual_engine_calls':1,'reference_only':True,'score_claim':None,'encrypted':args.encrypted,
             'backup':meta,'restored_files':len(hashes_before),'run_metrics':before['metrics'],'native_output_sql_sha256':core.sha(out/'restored/runs'/rid/'output/eplusout.sql')}
    core.write_json(out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
