"""Regression for a real 49k-token provider request from repeated tool schemas."""
import json

from backend.agent import TOOLS, TOOL_FIELDS, tool_parameters


def test_reader_schema_does_not_advertise_compute_plans():
    assert set(TOOLS) == set(TOOL_FIELDS)
    assert tool_parameters('weather_summary') == {
        'type': 'object', 'additionalProperties': False, 'properties': {}}
    assert set(tool_parameters('simulation_create')['properties']) == {'scheme_id', 'factor_profile_id'}
    assert '$defs' not in tool_parameters('simulation_create')
    assert len(json.dumps([tool_parameters(name) for name in TOOLS])) < 18000


def test_nested_plan_schemas_keep_all_referenced_definitions():
    for name in TOOLS:
        schema = tool_parameters(name)
        reached = set()

        def walk(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    ref = value['$ref'].removeprefix('#/$defs/')
                    assert ref in schema['$defs']
                    if ref not in reached:
                        reached.add(ref)
                        walk(schema['$defs'][ref])
                for key, child in value.items():
                    if key != '$defs':
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(schema)
        assert reached == set(schema.get('$defs', {}))
