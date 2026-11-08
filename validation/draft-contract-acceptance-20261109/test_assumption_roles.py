import pytest
from source_catalog import catalog
import tool_protocol

@pytest.mark.parametrize('text,dimension',[('非线弹性','negated_assumption'),('不能忽略自重','negated_assumption'),('不满足小挠度','negated_assumption'),('是否小挠度','uncertain_assumption'),('能否忽略自重','uncertain_assumption'),('核对线弹性适用范围','purpose_mention'),('检查小挠度适用性','purpose_mention'),('明确线弹性','assumption'),('声明忽略自重','assumption')])
def test_source_assertion_role(text,dimension):
 atoms=catalog(text).atoms
 assert len(atoms)==1 and atoms[0].dimension==dimension
 assert text[atoms[0].start:atoms[0].end]==atoms[0].quote

def test_question_negation_and_purpose_cannot_supply_beam_premise():
 stem='悬臂矩形梁跨5 m宽200 mm深300 mm模量30 GPa，集中力2 kN距固定端4 m，线弹性，忽略自重，'
 for tail in ['是否小挠度','不满足小挠度','检验小挠度适用性']:
  names=[t['function']['name'] for t in tool_protocol.tools(stem+tail)]
  assert 'propose_calculations' not in names

def test_purpose_is_retained_separately_from_asserted_condition():
 text='判断小挠度适用性；明确声明小挠度'
 rows=catalog(text).atoms
 assert [x.dimension for x in rows]==['purpose_mention','assumption']
 assert rows[0].start!=rows[1].start

def test_not_all_mentions_are_exempted_from_coverage():
 from coverage_guard import guard
 text='是否小挠度'
 r=guard(text,{'outcome':'draft','tasks':[]})
 assert r['outcome']=='clarify' and r['coverage']['unaccounted']
 assert not r['coverage']['nonparameter_purpose_mentions']
