from copy import deepcopy
import pytest
from evaluate import evaluate, match_count


def record():
    return {'image_id':'sample','source_sha256':'a'*64,'width':4,'height':4,
            'boxes':[{'category':'door','box':[0,0,2,2]}, {'category':'window','box':[2,0,4,2]}],
            'wall_mask':[[1,1,0,0],[1,1,0,0],[0,0,0,0],[0,0,0,0]]}


def test_hand_calculated_errors_and_duplicate_detection():
    ref=record();pred=deepcopy(ref)
    pred['boxes']=[{'category':'door','box':[0,0,2,2]}, {'category':'door','box':[0,0,2,2]}]
    pred['wall_mask']=[[1,1,1,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]]
    result=evaluate([ref],[pred])
    assert result['instances']['door']=={'tp':1,'fp':1,'fn':0,'precision':0.5,'recall':1.,'f1':2/3}
    assert result['instances']['window']=={'tp':0,'fp':0,'fn':1,'precision':None,'recall':0.,'f1':0.}
    assert result['wall']['micro_iou']==2/5
    assert (result['wall']['tp_pixels'],result['wall']['fp_pixels'],result['wall']['fn_pixels'])==(2,1,2)


def test_greedy_matching_trap_and_order_invariance():
    # Broad prediction can match either target; second prediction only target 0.
    # Taking the first valid edge without reassignment would undercount as 1.
    targets=[[0,0,2,2],[2,0,4,2]]
    guesses=[[0,0,4,2],[0,0,2,2]]
    assert match_count(targets,guesses,0.5)==2
    assert match_count(targets[::-1],guesses[::-1],0.5)==2


def test_missing_and_empty_are_not_perfect_scores():
    ref=record();result=evaluate([ref],[])
    assert result['missing_prediction_count']==1
    assert result['wall']['micro_iou']==0
    assert all(m['fn']==1 and m['f1']==0 for m in result['instances'].values())
    empty=record();empty['boxes']=[];empty['wall_mask']=[[0]*4 for _ in range(4)]
    result=evaluate([empty],[deepcopy(empty)])
    assert result['wall']['micro_iou'] is None
    assert all(m['f1'] is None for m in result['instances'].values())


def test_wrong_class_and_unknown_image():
    ref=record();pred=deepcopy(ref)
    pred['boxes']=[{'category':'window','box':[0,0,2,2]}]
    result=evaluate([ref],[pred])
    assert result['instances']['door']['fn']==1
    assert result['instances']['window']['fp']==1
    assert result['instances']['window']['fn']==1
    pred['image_id']='unknown'
    with pytest.raises(ValueError,match='unknown image'):evaluate([ref],[pred])


@pytest.mark.parametrize('change',[
    lambda r:r.update(source_sha256='b'*64),
    lambda r:r['boxes'][0].update(box=[0,0,float('nan'),2]),
    lambda r:r['boxes'][0].update(box=[0,0,5,2]),
    lambda r:r['boxes'][0].update(category='beam'),
    lambda r:r.update(wall_mask=[[0]]),
    lambda r:r['wall_mask'][0].__setitem__(0,255),
    lambda r:r.update(width=True),
])
def test_rejects_invalid_or_misbound_predictions(change):
    ref=record();pred=deepcopy(ref);change(pred)
    with pytest.raises(ValueError):evaluate([ref],[pred])


def test_duplicates_and_thresholds():
    ref=record()
    with pytest.raises(ValueError,match='Duplicate'):evaluate([ref,deepcopy(ref)],[])
    with pytest.raises(ValueError,match='Duplicate'):evaluate([ref],[ref,deepcopy(ref)])
    for threshold in [0,-1,2,True,float('nan')]:
        with pytest.raises(ValueError):evaluate([ref],[ref],threshold=threshold)


def test_micro_and_macro_iou_separately():
    ref=record();pred=deepcopy(ref)
    other=deepcopy(ref);other['image_id']='other';other['wall_mask']=[[1]*4 for _ in range(4)]
    guess=deepcopy(other);guess['wall_mask']=[[0]*4 for _ in range(4)]
    result=evaluate([ref,other],[pred,guess])
    assert result['wall']['micro_iou']==4/20
    assert result['wall']['macro_iou']==0.5
