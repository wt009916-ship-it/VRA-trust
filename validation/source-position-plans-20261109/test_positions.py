import copy,json
import pytest
import freeze_positions as fixture
import position_protocol as protocol
from source_catalog import catalog

def test_all_gold_roles_and_physics_preflight():
 assert len(fixture.CASES)==18
 for case in fixture.CASES:
  if case['gold_draft']:
   reviewed=protocol.review(case['message'],json.dumps(case['gold_draft'],ensure_ascii=False))
   assert reviewed['outcome']=='draft' and reviewed['guard'] is None
   assert [{k:v['ref'] for k,v in t['sources'].items()} for t in reviewed['tasks']]==[t['refs'] for t in case['expected']['tasks']]

def test_semantically_wrong_equal_value_positions_are_visible():
 case=fixture.CASES[5];draft=copy.deepcopy(case['gold_draft']);beam=draft['tasks'][0]
 assert beam['span_ref']!=beam['position_ref']
 beam['position_ref']=beam['span_ref']
 checked=protocol.review(case['message'],json.dumps(draft))
 assert checked['outcome']=='draft'  # Source existence is not semantic validation.
 assert checked['tasks'][0]['sources']['position']['ref']!=case['expected']['tasks'][0]['refs']['position']

def test_missing_parameter_is_application_clarification():
 case=fixture.CASES[0];d=copy.deepcopy(case['gold_draft']);d['tasks'][0]['rsi_ref']=None
 r=protocol.review(case['message'],json.dumps(d))
 assert r['outcome']=='clarify' and r['issue']=='missing_parameter' and not r['tasks'] and r['guard']

@pytest.mark.parametrize('tamper',['invented_ref','wrong_dimension','extra_number','duplicate_json'])
def test_untrusted_output_cannot_set_units_or_values(tamper):
 case=fixture.CASES[0];d=copy.deepcopy(case['gold_draft'])
 if tamper=='invented_ref':d['tasks'][0]['rsi_ref']='s999'
 if tamper=='wrong_dimension':d['tasks'][0]['rsi_ref']=d['tasks'][0]['layers'][0]['thickness_ref']
 if tamper=='extra_number':d['tasks'][0]['layers'][0]['value']=.2
 raw=json.dumps(d)
 if tamper=='duplicate_json':raw=raw[:-1]+',"outcome":"reject"}'
 with pytest.raises(Exception):protocol.review(case['message'],raw)

def test_numeric_invalidity_stays_visible_and_is_rejected():
 case=fixture.CASES[0];text=case['message'].replace('21 mm','-21 mm');d=case['gold_draft']
 r=protocol.review(text,json.dumps(d))
 assert r['outcome']=='reject' and r['issue']=='invalid_parameter' and not r['tasks']
 assert '-0.021' in r['guard']
 assert catalog(text).atoms[0].quote=='-21 mm'

def test_source_revision_is_not_reusable():
 from source_catalog import resolve
 text=fixture.CASES[0]['message'];source=catalog(text)
 with pytest.raises(ValueError):resolve(text+'追加修正',source.source_sha256,source.atoms[0].ref,source.atoms[0].dimension)
