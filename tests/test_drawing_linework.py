import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from backend.drawing_linework import analyse, interval_gap, segment


def raster(lines, size=(400, 300)):
    image = Image.new('RGB', size, 'white')
    draw = ImageDraw.Draw(image)
    for a, b in lines:
        draw.line((a, b), fill='black', width=1)
    return image


def test_real_hough_short_gap_is_only_hypothesis_and_original_pixels_unchanged():
    image = raster([((20, 80), (190, 80)), ((196, 80), (380, 80))])
    before = image.tobytes()
    result = analyse(image)
    assert image.tobytes() == before
    assert len(result['lines']) == 2 and len(result['gaps']) == 1
    gap = result['gaps'][0]
    assert gap['points_source_px'] == [[190.5, 80.5], [196.5, 80.5]]
    assert gap['gap_analysis_px'] == 6 and gap['observed_dark_fraction'] == 0
    assert gap['source_kind'] == 'INFERRED_GEOMETRY_NOT_ENGINEERING'
    assert all(line['building_component'] is None for line in result['lines'])
    assert not result['automatic_gap_fill'] and result['probability_of_correctness'] is None


def test_intentional_opening_and_damage_are_not_semantically_distinguishable():
    # Exactly the same pixels can represent a design opening or lost ink.
    opening = raster([((20, 50), (170, 50)), ((176, 50), (370, 50))])
    result = analyse(opening)
    assert len(result['gaps']) == 1 and result['gaps'][0]['review_required']
    assert not result['automatic_gap_fill']
    assert '设计开口' in result['gaps'][0]['interpretation']


def test_text_exclusion_cannot_be_reintroduced_as_a_gap_repair():
    image = raster([((20, 80), (190, 80)), ((196, 80), (380, 80))])
    result = analyse(image, [[[190, 76], [196, 76], [196, 84], [190, 84]]])
    assert result['gaps'] == []


@pytest.mark.parametrize('other', [[196, 85, 380, 85], [210, 80, 380, 80], [180, 80, 380, 80], [196, 80, 196, 220]])
def test_offset_large_opening_overlap_and_corner_do_not_become_collinear_gaps(other):
    assert interval_gap(segment([20, 80, 190, 80]), segment(other)) is None


def test_diagonal_gap_uses_euclidean_distance_and_source_pixel_centres():
    expected = math.sqrt(50)
    gap = interval_gap(segment([20, 20, 140, 140]), segment([145, 145, 260, 260]))
    assert gap[2] == pytest.approx(expected)
    result = analyse(raster([((20, 20), (140, 140)), ((145, 145), (260, 260))]))
    assert any(g['gap_analysis_px'] == pytest.approx(expected) for g in result['gaps'])


def test_blank_and_parallel_lines_do_not_imply_absent_walls_or_connect_parallel_strokes():
    empty = analyse(Image.new('RGB', (400, 300), 'white'))
    assert empty['status'] == 'no_lines_detected_not_proof_of_absence'
    parallel = analyse(raster([((20, 80), (380, 80)), ((20, 84), (380, 84))]))
    assert len(parallel['lines']) == 2 and not parallel['gaps']


def test_preview_downsampling_does_not_change_source_analysis_coordinates(tmp_path):
    image = Image.new('RGB', (3200, 1800), 'white')
    ImageDraw.Draw(image).line((100, 400, 3000, 400), fill='black', width=4)
    preview = tmp_path/'preview.png'
    result = analyse(image, preview_path=preview)
    assert result['analysis_size'] == [3200, 1800]
    assert result['preview_size'] == [1600, 900] and Image.open(preview).size == (1600, 900)
    assert result['analysis_to_source'] == [1, 0, 0, 0, 1, 0]
    assert result['lines']
    assert all(abs(p[1]-400) <= 4 for row in result['lines'] for p in row['points_source_px'])


def test_excess_native_candidates_and_invalid_polygons_fail_explicitly(monkeypatch):
    import cv2
    monkeypatch.setattr(cv2, 'HoughLinesP', lambda *a, **kw: np.tile([0, 0, 100, 0], (4097, 1)))
    result = analyse(raster([((20, 80), (380, 80))]))
    assert result['status'] == 'line_budget_exceeded' and result['truncated']
    assert not result['lines'] and not result['gaps']
    with pytest.raises(ValueError, match='polygon'):
        analyse(Image.new('RGB', (400, 300), 'white'), [[[0, 0], [float('nan'), 0], [5, 5], [0, 5]]])


def test_one_pixel_short_lines_survive_large_source_and_tile_boundaries():
    image = raster([((880, 500), (936, 500)), ((2000, 895), (2000, 947))], size=(3600, 2400))
    result = analyse(image)
    assert result['preview_size'][0] == 1600
    assert any(line['points_source_px'] == [[880.5, 500.5], [936.5, 500.5]] for line in result['lines'])
    assert any(line['points_source_px'] == [[2000.5, 895.5], [2000.5, 947.5]] for line in result['lines'])
    assert not result['gaps'] and not result['truncated']


def test_oblique_short_line_at_tile_seam_uses_source_ink():
    result = analyse(raster([((884, 884), (940, 940))], size=(2100, 1800)))
    assert any(line['points_source_px'] == [[884.5, 884.5], [940.5, 940.5]] for line in result['lines'])
    assert not result['gaps']


def test_source_exclusion_and_gap_length_are_not_scaled_with_preview():
    image = raster([((800, 500), (940, 500)), ((946, 500), (1100, 500))], size=(3200, 1800))
    result = analyse(image)
    assert len(result['gaps']) == 1 and result['gaps'][0]['gap_source_px'] == 6
    masked = analyse(image, [[[939, 497], [947, 497], [947, 503], [939, 503]]])
    assert not masked['gaps']


def test_dense_source_stops_at_raw_budget_without_returning_unverified_partial_lines():
    result = analyse(Image.new('RGB', (4200, 100), 'black'))
    assert result['status'] == 'line_budget_exceeded' and result['truncated']
    assert result['raw_line_count'] == 4097 and not result['lines']
