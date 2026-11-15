import json
from pathlib import Path
import urllib.error
import urllib.request

BASE = Path(__file__).parent/'public-sources'
BASE.mkdir(exist_ok=True)
sources = [('octagon-house', 'https://www.loc.gov/resource/hhh.dc0195.sheet/?fo=json&sp=3'),
           ('octagon-ice-house', 'https://www.loc.gov/resource/hhh.dc0938.sheet/?fo=json&sp=4')]
receipt = []
for name, url in sources:
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'VRA-Trust public-reference-validation/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(5*1024*1024+1)
        assert len(raw) <= 5*1024*1024
        value = json.loads(raw)
        (BASE/(name+'-metadata.json')).write_bytes(raw)
        item = value.get('item', {})
        row = {'name': name, 'url': url, 'ok': True, 'title': item.get('title'),
               'rights': item.get('rights'), 'files_groups': len(value.get('files', [])),
               'resources': value.get('resource', {})}
        receipt.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'resources'}, ensure_ascii=False), flush=True)
    except (urllib.error.URLError, ValueError, AssertionError) as error:
        row = {'name': name, 'url': url, 'ok': False, 'error': str(error)}
        receipt.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
(BASE/'metadata-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
