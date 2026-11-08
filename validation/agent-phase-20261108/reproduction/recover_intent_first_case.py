"""Recover the one completed model task from its isolated DB, read-only."""
import hashlib,json,sqlite3
from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-intent-api-f0a64d006212467abe26ed57238cbf49/api')
out=Path('C:/Users/18483/AppData/Local/Temp/vra-next-intent-pair-20261108')
with sqlite3.connect(root.joinpath('vra.sqlite3').as_uri()+'?mode=ro',uri=True) as con:
    agents=con.execute("SELECT body FROM records WHERE kind='agent' ORDER BY revision DESC LIMIT 1").fetchall()
    assert len(agents)==1
    task=json.loads(agents[0][0]);assert task['status']=='succeeded'
    assert task['question']=='请报这份清单中材料运输阶段的排放量，单位kgCO2e。只列数值和单位。'
    rid=task['read_requests'][0]['record_id']
    record=json.loads(con.execute("SELECT body FROM records WHERE kind='lifecycle' AND id=? ORDER BY revision DESC LIMIT 1",(rid,)).fetchone()[0])
target=out/'recovered-I01.json';assert not target.exists()
target.write_text(json.dumps(dict(task=task,source=record,method='Read-only recovery of completed I01; no model rerun',database=str(root/'vra.sqlite3')),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'recovered':'I01','status':task['status'],'artifact_keys':list(task['answer']['artifacts'][0]),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
