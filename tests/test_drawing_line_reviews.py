import base64
import hashlib
import io
import json
from xml.etree import ElementTree

from PIL import Image, ImageDraw

from test_api import create_project
from test_cad import upload


def source_png():
    image = Image.new('RGB', (400, 300), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((20, 80, 190, 80), fill='black', width=1)
    draw.line((196, 80, 380, 80), fill='black', width=1)
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def test_real_isolated_analysis_review_export_source_withdrawal_and_no_engineering_writes(client):
    project = create_project(client)
    pid = project['project_id']
    raw = source_png()
    fid = upload(client, pid, 'independent-line-gap.png', raw)
    base = f'/api/projects/{pid}/drawings'
    response = client.post(base, json={'file_id': fid, 'processing': {'line_analysis': True, 'median_filter': True}})
    assert response.status_code == 201, response.text
    drawing = response.json()
    did = drawing['drawing_id']
    url = base+'/'+did
    work = drawing['result']['linework']
    assert work and work['original_pixels_modified'] is False
    processed = Image.open(io.BytesIO(client.get(url+'/preview.png').content)).convert('L')
    assert processed.getextrema() == (255, 255)  # Filter destroys these one-pixel lines; analysis must use the original.
    assert len(work['gaps']) == 1 and work['gaps'][0]['gap_analysis_px'] == 6
    assert drawing['result']['resource_limits']
    before = client.app.state.domain.store.get('project', pid)
    geometry_hash = drawing['geometry_basis_hash']
    basis = '依据原图仅保留该几何假设，未核实是否设计开口。<script>alert(1)</script>'
    body = {'expected_revision': drawing['revision'], 'candidate_id': work['gaps'][0]['candidate_id'],
            'decision': 'retain_hypothesis', 'basis': basis}
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(url+'/line-review', json=body).status_code == 403
    assert client.get(url).json()['revision'] == drawing['revision']
    client.headers['X-CSRF-Token'] = csrf
    response = client.post(url+'/line-review', json=body)
    assert response.status_code == 200, response.text
    revised = response.json()
    review = revised['line_reviews'][body['candidate_id']]
    assert review['engineering_validated'] is False and review['reviewer_id']
    assert revised['geometry_basis_hash'] == geometry_hash
    assert client.post(url+'/line-review', json=body).status_code == 409
    exported = client.get(url+'/line-overlay.svg')
    assert exported.status_code == 200 and 'attachment' in exported.headers['content-disposition']
    assert exported.headers['content-type'] == 'image/svg+xml'
    assert '<script>' not in exported.text and '&lt;script&gt;' in exported.text
    xml = ElementTree.fromstring(exported.content)
    assert xml.attrib['viewBox'] == '0 -70 640 370'
    ns = {'s': 'http://www.w3.org/2000/svg'}
    meta = json.loads(xml.find('s:metadata', ns).text)
    assert meta['source_hash'] == hashlib.sha256(raw).hexdigest()
    assert meta['revision'] == revised['revision'] and not meta['automatic_gap_fill']
    assert meta['truncated'] is False and meta['gap_hypothesis_count'] == 1
    encoded = xml.find('s:image', ns).attrib['href'].split(',', 1)[1]
    assert hashlib.sha256(base64.b64decode(encoded)).hexdigest() == work['preview_sha256']
    assert len(xml.findall('s:line', ns)) == 1
    assert xml.find('s:line', ns).attrib['stroke'] == '#c13535'
    body.update(expected_revision=revised['revision'], decision='reject_hypothesis')
    assert client.post(url+'/line-review', json=body).status_code == 200
    rejected = ElementTree.fromstring(client.get(url+'/line-overlay.svg').content)
    assert rejected.findall('s:line', ns) == []
    history = client.get(url+'/history').json()
    assert [r['revision'] for r in history] == [1, 2, 3]
    assert history[1]['last_line_review']['decision'] == 'retain_hypothesis'
    body.update(expected_revision=3, candidate_id='gap_999')
    assert client.post(url+'/line-review', json=body).status_code == 409
    domain = client.app.state.domain
    assert domain.store.get('project', pid) == before
    assert not domain.store.list('evidence', pid)
    assert domain.file_record(pid, fid)[1].read_bytes() == raw
    other = create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/drawings/{did}/line-overlay.svg').status_code == 409
    path = domain.store.root/drawing['derivatives']['linework-preview.png']['path']
    path.write_bytes(b'isolated derivative tamper')
    stale = client.get(url).json()
    assert stale['result'] is None and stale['line_reviews'] is None
    assert client.get(url+'/line-overlay.svg').status_code == 409
    assert client.post(url+'/line-review', json={**body, 'candidate_id': 'gap_1'}).status_code == 409
    assert domain.file_record(pid, fid)[1].read_bytes() == raw
    client.cookies.clear()
    assert client.get(url+'/line-overlay.svg').status_code == 401
