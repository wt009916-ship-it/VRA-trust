"""Analytic centroidal properties for explicitly dimensioned symmetric sections.

No catalogue lookup, material inference, or resistance/safety assessment.
Dimensions are SI metres; X/Y are the profile's local centroidal axes.
"""
import math

KEYS = {
    'rectangle': {'b', 'h'},
    'circle': {'r'},
    'rectangular_hollow': {'b', 'h', 't'},
    'circular_hollow': {'r', 't'},
    'i_section': {'b', 'h', 'tw', 'tf', 'r'},
}


def properties(kind, dimensions):
    if kind not in KEYS or not isinstance(dimensions, dict) or set(dimensions) != KEYS[kind]:
        raise ValueError('Missing or unknown section dimensions')
    d = {}
    for key, value in dimensions.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Section dimensions must be finite numbers')
        minimum = 0 if kind == 'i_section' and key == 'r' else 1e-6
        if not minimum <= value <= 1000:
            raise ValueError('Section dimension outside supported SI range')
        d[key] = float(value)
    if kind in {'rectangle', 'rectangular_hollow', 'i_section'}:
        b, h = d['b'], d['h']
    else:
        b = h = 2*d['r']
    if kind == 'rectangle':
        area, ix, iy = b*h, b*h**3/12, h*b**3/12
        formula = 'A=b*h; Ix=b*h^3/12; Iy=h*b^3/12'
    elif kind == 'circle':
        area = math.pi*d['r']**2
        ix = iy = math.pi*d['r']**4/4
        formula = 'A=pi*r^2; Ix=Iy=pi*r^4/4'
    elif kind == 'rectangular_hollow':
        t = d['t']
        if 2*t >= min(b, h):
            raise ValueError('Hollow section thickness must leave a positive cavity')
        bi, hi = b-2*t, h-2*t
        area = 2*t*(b+h-2*t)
        ix = 2*t*(b*(h*h+h*hi+hi*hi)+hi**3)/12
        iy = 2*t*(h*(b*b+b*bi+bi*bi)+bi**3)/12
        formula = 'Sharp corners only; A=b*h-(b-2t)*(h-2t); Ix=(b*h^3-(b-2t)*(h-2t)^3)/12; Iy with b/h exchanged'
    elif kind == 'circular_hollow':
        r, t = d['r'], d['t']
        if t >= r:
            raise ValueError('Circular hollow thickness must be less than outer radius')
        ri = r-t
        area = math.pi*t*(r+ri)
        ix = iy = area*(r*r+ri*ri)/4
        formula = 'A=pi*(r^2-(r-t)^2); Ix=Iy=pi*(r^4-(r-t)^4)/4'
    else:
        tw, tf, r = d['tw'], d['tf'], d['r']
        if tw >= b or 2*tf >= h or r > min((b-tw)/2, (h-2*tf)/2):
            raise ValueError('Invalid I section web, flange or root fillet dimensions')
        # Each root addition is a square minus a quarter-disc centered at (r,r).
        # A, first and second raw moments about the concave corner (u,v).
        a = r*r*(1-math.pi/4)
        first = r**3*(5/6-math.pi/4)
        second = r**4*(1-5*math.pi/16)
        x0, y0 = tw/2, h/2-tf
        area = 2*b*tf+(h-2*tf)*tw+4*a
        ix = 2*(b*tf**3/12+b*tf*((h-tf)/2)**2)+tw*(h-2*tf)**3/12+4*(a*y0*y0-2*y0*first+second)
        iy = 2*tf*b**3/12+(h-2*tf)*tw**3/12+4*(a*x0*x0+2*x0*first+second)
        formula = 'Symmetric I: two flange rectangles + web rectangle + four root fillets (square minus quarter-disc); no flange slope/edge fillet'
    values = (area, ix, iy, b, h)
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Invalid or nonfinite section result')
    return {'kind': kind, 'dimensions_m': d, 'area_m2': area, 'ix_m4': ix, 'iy_m4': iy,
            'ixy_m4': 0., 'width_m': b, 'depth_m': h, 'centroid_profile_m': [0., 0.],
            'cx_m': b/2, 'cy_m': h/2, 'formula': formula,
            'method': 'analytic_parameterized_symmetric_profile',
            'structural_safety': 'NOT_ASSESSED'}
