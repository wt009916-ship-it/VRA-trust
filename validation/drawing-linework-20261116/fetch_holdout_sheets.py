from pathlib import Path
import hashlib
import json
import urllib.request
from PIL import Image

BASE = Path(__file__).parent/'public-sources'
sources = [
    {'name': 'twelfth-meeting-house.jpg', 'size': [1024, 806], 'sha1': 'b631ec73807304e4cf6b725a9e48339a5617b486',
     'url': 'https://upload.wikimedia.org/wikipedia/commons/d/d6/HABS_PA%2C51-PHILA%2C674-sheet2.jpg',
     'page': 'https://commons.wikimedia.org/w/index.php?title=File:HABS_PA,51-PHILA,674-sheet2.jpg&oldid=1232321583',
     'reported_rights': 'Public domain, US federal government work, as reported by Commons.',
     'source_kind': 'Host original JPEG; 1971 cellar and first-floor plan'},
    {'name': 'tudor-place-3840.jpg', 'size': [3840, 3071],
     'url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/10/HABS_Measured-drawing-of-Tudor-Place-Ground-Floor-Plan-1999.jpg/3840px-HABS_Measured-drawing-of-Tudor-Place-Ground-Floor-Plan-1999.jpg',
     'page': 'https://commons.wikimedia.org/w/index.php?title=File:HABS_Measured-drawing-of-Tudor-Place-Ground-Floor-Plan-1999.jpg&oldid=1287967663',
     'reported_rights': 'CC0 1.0 as reported by Commons; no independent rights/authenticity certification.',
     'source_kind': 'Host-generated 3840px derivative, NOT the original 7502x6000 raster; 1999 ground floor'}]
receipts = []
for source in sources:
    target = BASE/source['name']
    assert not target.exists()
    row = {**source, 'scope': 'Local public reference validation; no training or image redistribution in repository'}
    try:
        request = urllib.request.Request(source['url'], headers={'User-Agent': 'VRA-Trust public-reference-validation/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(10*1024*1024+1)
        assert len(raw) <= 10*1024*1024
        if source.get('sha1'):
            assert hashlib.sha1(raw).hexdigest() == source['sha1']
        target.write_bytes(raw)
        with Image.open(target) as image:
            assert list(image.size) == source['size']
        row.update(downloaded=True, byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        row.update(downloaded=False, error=type(exc).__name__, message=str(exc))
    receipts.append(row)
receipt = BASE/'holdout-source-receipts.json'
assert not receipt.exists()
receipt.write_text(json.dumps(receipts, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipts))
