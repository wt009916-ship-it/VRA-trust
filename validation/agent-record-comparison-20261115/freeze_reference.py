"""Independent preimplementation arithmetic; not an application test result."""
import hashlib,json
from fractions import Fraction as F
from decimal import Decimal,localcontext
from pathlib import Path
root=Path(__file__).parent
with localcontext() as ctx:
    ctx.prec=50
    def decimal(value):return str(Decimal(value.numerator)/Decimal(value.denominator))
    a=F(12,100)+F(8,100)+F(2,10)/F(5,10)+F(4,100)/F(4,100)
    b=F(12,100)+F(8,100)+F(25,100)/F(5,10)+F(6,100)/F(4,100)
    assert a==F(8,5) and b==F(11,5)
    cases=[]
    for fact,x,y in [('total_resistance_m2k_w',a,b),('u_w_m2k',1/a,1/b)]:
        for label,baseline,candidate in [('forward',x,y),('reverse',y,x)]:
            cases.append({'id':fact+'_'+label,'baseline':decimal(baseline),'candidate':decimal(candidate),
                'difference':decimal(candidate-baseline),'relative_change_percent':decimal(100*(candidate-baseline)/baseline)})
    reference={'status':'independent answers only; product not implemented or tested',
        'thermal_inputs':{'films':[.12,.08],'A':[[.2,.5],[.04,.04]],'B':[[.25,.5],[.06,.04]]},
        'cases':cases,'zero_baseline':{'baseline':'0','candidate':'7.5','difference':'7.5','relative_change_percent':None},
        'incompatible':['different_currency','different_period','different_carrier','different_metric','cross_project'],
        'withdrawn_source':'no current values or derived differences',
        'numeric_tolerance':{'relative':1e-10,'absolute':1e-8},
        'scope':'mathematical comparison of source facts; not functional equivalence, annual savings or engineering safety'}
    path=root/'reference-frozen.json';assert not path.exists()
    path.write_text(json.dumps(reference,indent=2)+'\n')
    print(json.dumps({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'case_count':len(cases)}))
