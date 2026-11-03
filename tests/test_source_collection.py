"""Provider envelopes vary; preserve licenses and prevent wrong-query cache reuse."""
import json
from scripts import collect_material_sources as collect


def test_string_license_and_query_bound_cache(tmp_path,monkeypatch):
    raw=json.dumps({'hitCount':1,'resultList':{'result':[{'title':'Cerium oxide cement durability',
        'doi':'10.1234/synthetic-test','pubYear':'2020','license':'cc-by','isOpenAccess':'Y'}]}}).encode()
    requests=[]
    monkeypatch.setattr(collect,'request',lambda url:requests.append(url) or raw)
    monkeypatch.setattr(collect.time,'sleep',lambda seconds:None)
    first,logs=collect.retrieve(tmp_path,'europepmc',['cement'],'2026-11-02')
    assert first[0]['license_urls']==[] and first[0]['license_text']=='cc-by'
    assert first[0]['status']=='UNREVIEWED_DISCOVERY' and logs[0]['status']=='retrieved'
    again,logs=collect.retrieve(tmp_path,'europepmc',['cement'],'2026-11-02',True)
    assert len(requests)==1 and again==first and logs[0]['status']=='cached'
    wrong,logs=collect.retrieve(tmp_path,'europepmc',['different query'],'2026-11-02',True)
    assert not wrong and logs[0]['status']=='failed' and len(requests)==1
    assert (tmp_path/'europepmc-01.json').read_bytes()==raw
