import struct
import pytest
from wkb_reference import polygons,extent


@pytest.mark.parametrize('order,flag',[('<',1),('>',0)])
def test_rectangle_and_hole_in_both_byte_orders(order,flag):
    outer=[(0,0),(8,0),(8,6),(0,6),(0,0)]
    hole=[(2,2),(3,2),(3,4),(2,4),(2,2)]
    raw=struct.pack('B',flag)+struct.pack(order+'II',3,2)
    for ring in (outer,hole):
        raw+=struct.pack(order+'I',len(ring))
        raw+=b''.join(struct.pack(order+'dd',*p) for p in ring)
    decoded=polygons(raw.hex())
    assert decoded==[[[list(p) for p in outer],[list(p) for p in hole]]]
    assert extent(decoded[0])==[0,0,8,6]
    multi=struct.pack('<BII',1,6,2)+raw+raw
    assert polygons(multi.hex())==decoded*2
    with pytest.raises(ValueError,match='Trailing'):polygons((raw+b'X').hex())
    with pytest.raises(ValueError,match='Truncated'):polygons(raw[:-1].hex())


def test_empty_and_unsupported_geometry():
    assert polygons(struct.pack('<BII',1,6,0).hex())==[]
    with pytest.raises(ValueError,match='Unsupported'):polygons(struct.pack('<BII',1,2,0).hex())
    with pytest.raises(ValueError,match='count budget'):polygons(struct.pack('<BII',1,6,100001).hex())
