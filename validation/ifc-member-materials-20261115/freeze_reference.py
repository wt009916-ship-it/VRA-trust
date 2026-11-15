"""Freeze independent arithmetic before new member-material implementation."""
import json
import hashlib
from decimal import Decimal as D
from pathlib import Path

p=Path(__file__).with_name('reference-frozen.json')
assert not p.exists()
data={'frozen_before_implementation':True,'box':{'dimensions_m':[2,3,4], 'gross_m3':str(D(2)*3*4),
 'through_opening_dimensions_m':[.5,1,4], 'net_m3':str(D(2)*3*4-D('.5')*1*4)},
 'rectangular_hollow':{'outer_m':[.2,.3],'thickness_m':.01,'length_m':6,'volume_m3':str((D('.2')*D('.3')-D('.18')*D('.28'))*6)},
 'two_overlapping_members':{'each_box_m':[2,3,4],'x_separation_m':1,'sum_m3':'48','union_m3':'36','deduction_m3':'12'},
 'tolerance':{'planar_abs_m3':1e-8,'public_curved_relative':.005},
 'expected_refusals':['missing_material','ambiguous_material','heterogeneous_material','profile_body_mismatch','invalid_topology','missing_units'],
 'scope':'Model geometry and declared material only; not procurement or carbon certification'}
p.write_text(json.dumps(data,indent=2)+'\n')
print(hashlib.sha256(p.read_bytes()).hexdigest())
