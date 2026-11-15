from pathlib import Path
import hashlib
import json

BASE = Path(__file__).parent
ROOT = BASE.parents[1]/'.codex_work/vra-resource-leveling-20261115'
source = (BASE/'public_api.py').read_text(encoding='utf-8')
source = source.replace("def main():\n    out = BASE/'public-api-v1'", "def main(frozen_name, output_name):\n    out = BASE/output_name")
source = source.replace("(BASE/'public-frozen.json')", "(BASE/frozen_name)")
source = source.replace("(BASE/'public-sources/First_Floor_Plan_HABS.jpg')", "(BASE/frozen['source_file'])")
source = source.replace("if __name__ == '__main__':\n    main()", """if __name__ == '__main__':
    for frozen_name, output_name in [
        ('original-regression-v2-frozen.json', 'original-regression-v2'),
        ('twelfth-meeting-house-frozen.json', 'holdout-meeting-v2'),
        ('tudor-place-3840-frozen.json', 'holdout-tudor-v2')]:
        print(output_name, flush=True)
        main(frozen_name, output_name)""")
source = source.replace("reference_total=len(results),", "reference_total=len(results), reference_established=sum(r['reference_established'] for r in frozen['references']),")
source = source.replace("'reference_total', 'detected_lines'", "'reference_total', 'reference_established', 'detected_lines'")
target = BASE/'public_api_v2.py'
assert not target.exists()
target.write_text(source, encoding='utf-8')
snapshot = BASE/'source-v2-snapshot'
snapshot.mkdir(exist_ok=False)
hashes = {}
for name in ['drawing_linework.py', 'drawing_line_reviews.py', 'drawing_worker.py', 'drawings.py', 'parser_runtime.py']:
    raw = (ROOT/'backend'/name).read_bytes()
    (snapshot/name).write_bytes(raw)
    hashes[name] = hashlib.sha256(raw).hexdigest()
(snapshot/'manifest.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
print('Frozen source snapshot and three-run application harness; no new image application results inspected.')
