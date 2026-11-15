import hashlib
import json
from pathlib import Path
import urllib.request

BASE = Path(__file__).parent/'public-sources'
url = 'https://upload.wikimedia.org/wikipedia/commons/2/26/First_Floor_Plan_HABS.jpg'
path = BASE/'First_Floor_Plan_HABS.jpg'
assert not path.exists()
with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'VRA-Trust public-reference-validation/1.0'}), timeout=30) as response:
    raw = response.read(10*1024*1024+1)
assert len(raw) == 429929 and hashlib.sha1(raw).hexdigest() == '1ab043b2c485575c81098524fb452fd14db9f8a0'
path.write_bytes(raw)
receipt = {'url': url, 'page': 'https://commons.wikimedia.org/w/index.php?title=File:First_Floor_Plan_HABS.jpg&oldid=1253425626',
           'reported_title': 'First Floor Plan HABS', 'reported_date': 1934,
           'rights_as_reported_by_host': 'Public Domain Mark; US federal government work. No independent legal or source-authenticity certification.',
           'size': len(raw), 'sha1': hashlib.sha1(raw).hexdigest(), 'sha256': hashlib.sha256(raw).hexdigest(),
           'scope': 'Local public-reference validation only; no training and no raw image redistribution in repository',
           'prior_loc_metadata_requests': '403 responses retained; no claimed access to those two LOC records'}
(BASE/'image-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'size': receipt['size'], 'sha256': receipt['sha256']}))
