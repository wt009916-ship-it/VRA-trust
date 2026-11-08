from PIL import Image,ImageDraw
import pytest
from symbol_detector import detect,_iou


def fixture():
    image=Image.new('RGB',(256,256),'white');draw=ImageDraw.Draw(image)
    draw.line((10,120,50,120),fill='black',width=8)
    draw.line((84,120,240,120),fill='black',width=8)
    draw.arc((16,86,84,154),270,360,fill='black',width=1)
    draw.line((50,120,50,86),fill='black',width=2)
    draw.line((10,190,60,190),fill='black',width=8)
    draw.line((110,190,240,190),fill='black',width=8)
    draw.rectangle((60,186,110,194),outline='black',width=1)
    draw.line((60,190,110,190),fill='black',width=1)
    return image


@pytest.mark.parametrize('turn',range(4))
def test_constructed_symbol_locations_and_original_preservation(turn):
    image=fixture().rotate(90*turn);before=image.tobytes()
    result,mask=detect(image)
    assert image.tobytes()==before and mask.size==image.size
    doors=[c for c in result['candidates'] if c['category']=='door']
    windows=[c for c in result['candidates'] if c['category']=='window']
    def rotated(box):
        l,t,r,b=box
        for _ in range(turn):l,t,r,b=t,256-r,b,256-l
        return [l,t,r,b]
    assert len(doors)==1 and _iou(doors[0]['box'],rotated([49,85,85,121]))>0.7,result
    assert len(windows)==1 and _iou(windows[0]['box'],rotated([59,185,111,195]))>0.7,result
    assert all(c['review_required'] and c['confidence_probability'] is None for c in result['candidates'])


def test_negative_grid_and_invalid_image():
    for color in ('white','black'):
        result,mask=detect(Image.new('RGB',(256,256),color))
        assert result['status']=='insufficient_contrast' and not result['candidates'] and mask.getbbox() is None
    image=Image.new('RGB',(256,256),'white');draw=ImageDraw.Draw(image)
    for p in range(10,250,20):
        draw.line((10,p,240,p),fill='black',width=1);draw.line((p,10,p,240),fill='black',width=1)
    result,mask=detect(image)
    assert not result['candidates'] and mask.getbbox() is None
    with pytest.raises(ValueError):detect(Image.new('RGB',(12,12)))
