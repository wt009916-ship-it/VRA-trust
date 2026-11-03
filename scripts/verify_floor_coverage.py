"""Measure the entire visible floor footprint against a separately traced reference."""
import argparse
from pathlib import Path
import sys

from shapely.geometry import Point, Polygon, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import core
from backend.floorplan import recognize
from backend.model_schema import ImportOptions


def coverage(result, reference):
    metadata = result['metadata']
    if metadata['pixels'] != reference['pixels']:
        raise core.ValidationError('Reference and result use different raster sizes')
    factor = metadata['scale_to_m']
    expected = Polygon(reference['envelope_px'], reference.get('holes_px', []))
    if not expected.is_valid or expected.is_empty or expected.area <= 0:
        raise core.ValidationError('Review envelope must be a valid nonempty polygon')
    rooms = [(r['id'], Polygon(r['drawing']['polygon_px'], r['drawing'].get('interior_islands_px', []))) for r in result['rooms']]
    found = unary_union([p for _, p in rooms])
    missing, outside = expected.difference(found), found.difference(expected)
    scale = factor**2
    return {'candidate_count': len(rooms), 'envelope_m2': expected.area*scale,
            'covered_m2': expected.intersection(found).area*scale, 'missed_m2': missing.area*scale,
            'outside_m2': outside.area*scale, 'coverage_fraction': 1-missing.area/expected.area,
            'overlap_m2': max(0., sum(p.area for _, p in rooms)-found.area)*scale,
            'intersection_over_union': expected.intersection(found).area/expected.union(found).area,
            'uncovered_geometry_px': mapping(missing), 'outside_geometry_px': mapping(outside),
            'anchors': [{'name': a['name'], 'point_px': a['point_px'],
                         'candidate_ids': [rid for rid, p in rooms if p.covers(Point(a['point_px']))]}
                        for a in reference.get('anchors', [])],
            'status': 'FOOTPRINT_DIAGNOSTIC_ONLY', 'room_accuracy': None,
            'basis': 'Separately traced approximate interior envelope; uncovered regions include walls, fixtures and missed rooms. Not a surveyed room boundary set.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--options', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    reference = core.read_json(a.reference)
    options = ImportOptions.model_validate(core.read_json(a.options))
    if reference['source_sha256'] != core.sha(a.pdf) or reference['page'] != options.page:
        raise core.ValidationError('Reference original/hash/page do not match recognition input')
    a.out.mkdir(parents=True, exist_ok=False)
    output = recognize(a.pdf, options)
    result = coverage(output, reference)
    core.write_json(a.out/'recognition.json', output)
    core.write_json(a.out/'coverage.json', {**result, 'reference': reference, 'reference_sha256': core.sha(a.reference),
                                         'options': options.model_dump()})
    print('Candidates', result['candidate_count'], 'footprint coverage', round(result['coverage_fraction']*100, 2))


if __name__ == '__main__':
    main()
