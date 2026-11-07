"""Read pinned upstream source for the next benchmark; do not execute it."""
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='vra-designload-sources-'))
records = []
for filename in ('SQLiteProcedures.cc', 'ZoneEquipmentManager.cc'):
    url = 'https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/v9.0.1/src/EnergyPlus/' + filename
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read(5_000_001)
    assert len(raw) < 5_000_001
    path = root / filename
    path.write_bytes(raw)
    lines = raw.decode('utf-8').splitlines()
    matches = [i for i, line in enumerate(lines) if any(term in line for term in
               ('CalcDesLoad', 'UserDesLoad', 'createSQLiteZoneSizingRecord', 'Calculated Design Load', 'User Design Load'))]
    excerpts = [{'line': i + 1, 'text': '\n'.join(lines[max(0, i-2):min(len(lines), i+4)])} for i in matches]
    records.append({'url': url, 'local_source': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'bytes': len(raw), 'read_only': True, 'excerpts': excerpts})
out = Path(__file__).parent / 'source-discovery-v1.json'
with out.open('x', encoding='utf-8') as stream:
    json.dump({'sources': records, 'status': 'research only; no product load output validated'}, stream, indent=2)
print(json.dumps({'sources': [{'file': Path(r['local_source']).name, 'bytes': r['bytes'], 'matches': len(r['excerpts'])} for r in records]}))
