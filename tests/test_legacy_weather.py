"""Legacy format support must not accept truncation, hide absence or alter bytes."""
import csv
import hashlib

import pytest

from backend import core
from backend.input_validation import validate_epw


def source_rows():
    with (core.ROOT / 'fixtures/demo/reference_5zone/weather.epw').open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.reader(stream))


def write(tmp_path, rows):
    path = tmp_path / 'weather.epw'
    with path.open('w', encoding='utf-8', newline='') as stream:
        csv.writer(stream).writerows(rows)
    return path


def legacy_rows():
    rows = source_rows()
    return rows[:8] + [r[:32] for r in rows[8:]]


def test_absent_legacy_fields_are_unknown_and_original_is_preserved(tmp_path):
    path = write(tmp_path, legacy_rows())
    before = path.read_bytes()
    result = validate_epw(path)
    assert result['record_field_count'] == 32
    assert result['hours'] == 8760 and result['status'] == 'accepted_with_conditions'
    assert result['application_imputation_count'] == 0
    assert result['source_sha256'] == hashlib.sha256(before).hexdigest()
    assert path.read_bytes() == before
    for name in ('albedo', 'liquid_precipitation_depth', 'liquid_precipitation_quantity'):
        field = result['fields'][name]
        assert field['present_count'] == 0 and field['missing_count'] == 8760
        assert field['min'] is None and field['max'] is None
        condition = next(c for c in result['conditions'] if c['field'] == name)
        assert condition['code'] == 'LEGACY_COLUMN_ABSENT'
        assert (condition['count'], condition['first_line'], condition['last_line']) == (8760, 9, 8768)
        assert '未观测' in condition['message'] and '不等于零' in condition['message']


@pytest.mark.parametrize('width', [31, 33, 34, 36])
def test_other_truncated_or_extended_formats_rejected(tmp_path, width):
    rows = source_rows()
    rows[8] = (rows[8] + ['0'])[:width]
    with pytest.raises(core.ValidationError, match='EPW line 9.*record'):
        validate_epw(write(tmp_path, rows))


@pytest.mark.parametrize('legacy_first', [False, True])
def test_mixed_formats_rejected(tmp_path, legacy_first):
    rows = source_rows()
    rows[8 if legacy_first else 9] = rows[8 if legacy_first else 9][:32]
    with pytest.raises(core.ValidationError, match='EPW line 10.*列数必须一致'):
        validate_epw(write(tmp_path, rows))


@pytest.mark.parametrize('column,value', [(6, '99.9'), (9, '101.325'), (14, '9999'), (31, ''), (31, 'NaN')])
def test_legacy_does_not_relax_present_field_validation(tmp_path, column, value):
    rows = legacy_rows()
    rows[8][column] = value
    with pytest.raises(core.ValidationError, match='EPW line 9'):
        validate_epw(write(tmp_path, rows))


def test_modern_weather_retains_observations(tmp_path):
    rows = source_rows()
    for row in rows[8:]:
        row[32:35] = ['0.25', '0', '1']
    result = validate_epw(write(tmp_path, rows))
    assert result['record_field_count'] == 35
    assert result['fields']['albedo']['min'] == .25
    assert result['fields']['liquid_precipitation_depth']['missing_count'] == 0
    assert not any(c['code'] == 'LEGACY_COLUMN_ABSENT' for c in result['conditions'])
