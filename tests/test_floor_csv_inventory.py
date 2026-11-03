import pytest

from backend import core
from test_model_workbench import project


def test_source_csv_reports_invalid_topology_without_inventing_units_or_repair(client):
    pid=project(client);d=client.app.state.domain
    text='type,name,geometry\nIfcSpace,room,"POLYGON ((0 0, 4 0, 4 3, 0 3, 0 0))"\nIfcWall,bad,"POLYGON ((0 0, 1 1, 0 1, 1 0, 0 0))"\nIfcDoor,missing,invalid\n'
    src=d.add_file(pid,'source.csv',text.encode())
    result=client.app.state.agent.call(pid,'floor_csv_inventory',{'file_id':src['file_id']},False)
    assert result['source_type_counts']=={'IfcSpace':1,'IfcWall':1,'IfcDoor':1}
    assert result['geometry_issues']=={'invalid_polygon_topology':1,'invalid_wkt':1}
    assert result['units'] is None and result['height_m'] is None
    assert not result['thermal_model_ready'] and result['repairs_applied']==0
    assert result['issue_examples'][0]['row']==3
    assert result['issue_type_counts']['invalid_polygon_topology']=={'IfcWall':1}
    assert result['issue_examples_omitted_rows']==0 and result['affected_rows']==2
    with pytest.raises(core.ValidationError):
        client.app.state.agent.call(project(client),'floor_csv_inventory',{'file_id':src['file_id']},False)


def test_meter_csv_is_not_mistaken_for_floor_geometry(client):
    pid=project(client);d=client.app.state.domain;src=d.add_file(pid,'meter.csv',b'time,power\n2025-01-01,3')
    with pytest.raises(core.ValidationError):client.app.state.agent.call(pid,'floor_csv_inventory',{'file_id':src['file_id']},False)
