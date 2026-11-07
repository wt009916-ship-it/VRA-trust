import hashlib,json,sqlite3
from pathlib import Path
out=Path(__file__).resolve().parent
plan=json.loads((out/'browser-prepared-v1.json').read_text())
root=Path(plan['root'])/'api'
did='drawing_e02566dfce64450eb0c4f41eb0186f08'
target=root/'drawings'/did/'source-preview.png'
assert target.resolve().is_relative_to(root.resolve())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def records():
    with sqlite3.connect('file:'+ (root/'vra.sqlite3').as_posix()+'?mode=ro',uri=True) as con:
        rows=con.execute('SELECT kind,id,revision,project_id,body FROM records ORDER BY kind,id,revision').fetchall()
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()
before=records();original=root/'files/file_54b49ecb36a547949330e0d059f4a648.png'
assert sha(original)=='24b96e41329f56cb6a1de5e6d5ffbbb3cef8ea8a828fd7a379276b4b9f7508eb'
raw=target.read_bytes();backup=Path(plan['root'])/'derivative-before-tamper-v1.png'
with backup.open('xb') as f:f.write(raw)
target.write_bytes(raw+b'\ncontrolled isolated derivative integrity test\n')
assert records()==before and sha(original)==hashlib.sha256(raw).hexdigest()
receipt={'target':str(target),'backup':str(backup),'before_sha256':hashlib.sha256(raw).hexdigest(),
         'after_sha256':sha(target),'original_sha256':sha(original),'records_sha256_before_and_after':before,
         'scope':'Only an isolated derived PNG modified; original source and append-only records unchanged. Not original 18772 runtime.'}
with (out/'derivative-tamper-v1.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt))
