"""Regional archive contracts; no project or geotechnical qualification implied."""
from backend import core
from test_weather import project, reference_path


def test_regional_empty_then_search_download_and_integrity(client):
    pid = project(client)
    url = f'/api/projects/{pid}/weather/regional'
    assert client.get(url).json()['items'] == []
    root = client.app.state.domain.store.root/'regional-context'
    (root/'epw').mkdir(parents=True)
    key = 'a'*64
    raw = reference_path().read_bytes()
    epw = root/'epw'/f'{key}.epw'
    epw.write_bytes(raw)
    geo = root/'geology.json'
    core.write_json(geo, {'Example': {'name': 'Test formation', 'province': 'Jiangxi', 'period': 'Jurassic', 'lithology_pattern': 'sandstone'}})
    core.write_json(root/'catalogue.json', {'coverage': {}, 'sources': {'CHN': {'url': 'https://climate.onebuilding.org/'},
        'geology': {'sha256': core.sha(geo)}}, 'weather': [{'id': key, 'region': 'JX', 'name': 'QA fixture',
        'station': '123456', 'edition': 'Fixture', 'status': 'QA_PASSED', 'epw_sha256': core.sha(epw)}]})
    assert client.get(url, params={'region': '江西'}).json()['total'] == 1
    assert client.get(url, params={'kind': 'geology', 'region': 'Jiangxi', 'query': 'sandstone'}).json()['total'] == 1
    assert client.get(url+'/'+key+'.epw').content == raw
    epw.write_bytes(raw+b'\n')
    assert client.get(url+'/'+key+'.epw').status_code == 409
    geo.write_bytes(geo.read_bytes()+b'\n')
    assert client.get(url, params={'kind': 'geology'}).status_code == 409
    client.cookies.clear()
    assert client.get(url).status_code == 401
    assert client.get(url+'/'+key+'.epw').status_code == 401
