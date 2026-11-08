"""Decode bounded 2-D Polygon/MultiPolygon WKB for public reference rendering."""
import math
import struct


def polygons(hex_bytes):
    raw=bytes.fromhex(hex_bytes)
    if len(raw)>10_000_000:raise ValueError('Geometry too large')
    cursor=0
    def read(fmt):
        nonlocal cursor
        size=struct.calcsize(fmt)
        if cursor+size>len(raw):raise ValueError('Truncated WKB')
        result=struct.unpack_from(fmt,raw,cursor);cursor+=size
        return result
    def geometry(depth=0):
        if depth>8:raise ValueError('Geometry nesting budget')
        flag=read('B')[0]
        if flag not in (0,1):raise ValueError('Invalid byte order')
        order='<' if flag else '>'
        kind=read(order+'I')[0]
        count=read(order+'I')[0]
        if count>100_000:raise ValueError('Geometry count budget')
        if kind==3:
            rings=[]
            for _ in range(count):
                n=read(order+'I')[0]
                if not 4<=n<=100_000:raise ValueError('Invalid polygon ring')
                ring=[list(read(order+'dd')) for _ in range(n)]
                if ring[0]!=ring[-1] or not all(math.isfinite(x) for p in ring for x in p):
                    raise ValueError('Open/nonfinite ring')
                rings.append(ring)
            return [rings] if rings else []
        if kind in (6,7):
            return [polygon for _ in range(count) for polygon in geometry(depth+1)]
        raise ValueError(f'Unsupported WKB geometry {kind}')
    result=geometry()
    if cursor!=len(raw):raise ValueError('Trailing geometry bytes')
    return result


def extent(polygon):
    points=[p for ring in polygon for p in ring]
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
