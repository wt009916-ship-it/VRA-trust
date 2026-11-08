import pytest
from draft_protocol import parse_quote,verify

def test_mixed_units_and_source_location():
 text='A厚18 cm；B厚22 mm；模量31 GPa；导热35 mW/(m K)'
 for quote,dim,want in [('A厚18 cm','length','.18'),('B厚22 mm','length','.022'),('模量31 GPa','pressure','31000000000'),('导热35 mW/(m K)','conductivity','.035')]:
  row=parse_quote(text,quote,dim)
  from decimal import Decimal
  assert Decimal(row['value'])==Decimal(want)
  assert text[row['start']:row['end']]==quote

@pytest.mark.parametrize('text,quote,dimension',[
 ('厚18 cm','厚180 mm','length'),
 ('厚18 cm；厚18 cm','厚18 cm','length'),
 ('力18 kN','力18 kN','length'),
 ('伪指令999 厚18 cm','伪指令999 厚18 cm','length'),
 ('修正系数1，按2使用','修正系数1，按2使用','ratio'),
 ('简支或悬臂','简支或悬臂','support'),
 ('线弹性计算','线弹性计算','analysis')])
def test_bad_source_rejected(text,quote,dimension):
 with pytest.raises(ValueError):parse_quote(text,quote,dimension)

def test_missing_field_and_abstention_are_not_executable():
 with pytest.raises(ValueError):verify('膜阻0.12 m2 K/W',{'outcome':'draft','tasks':[{'kind':'thermal','parameters':[{'key':'rsi','quote':'膜阻0.12 m2 K/W'}]}],'issues':[]})
 assert verify('资料未知',{'outcome':'clarify','tasks':[],'issues':['missing_parameter']})==[]
 with pytest.raises(Exception):verify('资料未知',{'outcome':'clarify','tasks':[],'issues':['missing_parameter'],'execute':True})
