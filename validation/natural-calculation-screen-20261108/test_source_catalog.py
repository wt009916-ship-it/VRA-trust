import pytest
from source_catalog import catalog,resolve,field_schema,strict_json,model_catalog

def test_repeated_equal_values_have_distinct_positions():
 text='跨度3.8 m，荷载位置3.8 m，厚度38 mm'
 source=catalog(text);lengths=[a for a in source.atoms if a.dimension=='length']
 assert len(lengths)==3 and len({a.ref for a in lengths})==3
 assert [float(a.value) for a in lengths]==[3.8,3.8,.038]
 assert all(text[a.start:a.end]==a.quote for a in lengths)
 assert resolve(text,source.source_sha256,lengths[1].ref,'length').start==text.rindex('3.8 m')

def test_revisions_and_unit_mismatch_rejected():
 text='厚度26 mm，荷载4.2 kN';source=catalog(text)
 with pytest.raises(ValueError):resolve(text+'更正',source.source_sha256,'s000','length')
 with pytest.raises(ValueError):resolve(text,source.source_sha256,'s000','force')
 with pytest.raises(ValueError):resolve(text,source.source_sha256,'s999','length')

def test_anchors_do_not_rewrite_or_merge_original_words():
 source=catalog('按小挠度分析；线弹性，忽略自重。悬臂')
 assert {a.value for a in source.atoms}=={'small_deflection','linear_elastic','no_self_weight','cantilever'}
 assert all(a.quote in '按小挠度分析；线弹性，忽略自重。悬臂' for a in source.atoms)

def test_no_guessed_unit_or_factor():
 source=catalog('厚度63，导热系数未知，纠正前是63 cm')
 assert len([a for a in source.atoms if a.dimension=='scalar'])==1
 assert field_schema(source,'conductivity')['enum']==[None]
 assert len(field_schema(source,'length')['enum'])==2
 # Catalog deliberately does NOT choose the obsolete value or claim intent verified.
 assert 'intent' in model_catalog(source)['warning']

@pytest.mark.parametrize('raw',['{"a":1,"a":2}','{"a":{"b":1,"b":2}}','{"a":NaN}','{"a":Infinity}'])
def test_duplicate_or_nonfinite_json_rejected(raw):
 with pytest.raises(ValueError):strict_json(raw)

@pytest.mark.parametrize('text',['', 'a'*4001,' '.join('2 m' for _ in range(161)),'厚1e999 m'])
def test_budget(text):
 with pytest.raises(ValueError):catalog(text)

def test_scale_and_negative_values_preserved_without_approval():
 source=catalog('厚-15 mm，导热43 mW/(m K)，模量29 GPa，膜阻0.09 m²K/W，修正1.1')
 assert [float(a.value) for a in source.atoms]==[-.015,.043,29000000000,.09,1.1]
 # Negative raw values remain visible for downstream rejection; no absolute value fix.
 assert source.atoms[0].quote=='-15 mm'

def test_decimal_conversion_does_not_round_source_precision():
 from decimal import Decimal
 text='厚度1.123456789012345678901234567890123456 mm'
 atom=catalog(text).atoms[0]
 assert Decimal(atom.value)==Decimal('0.001123456789012345678901234567890123456')
