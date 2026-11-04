"""Generated real-format fixtures with independent counts and distances."""
import io
import hashlib
import subprocess
import ezdxf
import ifcopenshell
import pytest
from backend.cad import Cad, Inspection
from backend import core
from test_api import create_project


def dxf_bytes(units=4):
    doc = ezdxf.new('R2010'); doc.units = units
    doc.modelspace().add_line((0, 0), (3000, 4000))
    doc.modelspace().add_text('<script>untrusted</script>')
    stream = io.StringIO(); doc.write(stream)
    return stream.getvalue().encode()


def ifc_bytes(duplicate=False):
    doc = ifcopenshell.file(schema='IFC4')
    unit = doc.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix='MILLI', Name='METRE')
    units = doc.create_entity('IfcUnitAssignment', Units=[unit])
    doc.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), Name='Independent fixture', UnitsInContext=units)
    floor = doc.create_entity('IfcBuildingStorey', GlobalId=ifcopenshell.guid.new(), Name='Level 1')
    wall = doc.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Wall A')
    doc.create_entity('IfcDoor', GlobalId=wall.GlobalId if duplicate else ifcopenshell.guid.new(), Name='Door B')
    doc.create_entity('IfcRelContainedInSpatialStructure', GlobalId=ifcopenshell.guid.new(), RelatedElements=[wall], RelatingStructure=floor)
    prop = doc.create_entity('IfcPropertySingleValue', Name='FireRating', NominalValue=doc.create_entity('IfcLabel', '2h'))
    pset = doc.create_entity('IfcPropertySet', GlobalId=ifcopenshell.guid.new(), Name='Pset_WallCommon', HasProperties=[prop])
    doc.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingPropertyDefinition=pset)
    return doc.to_string().encode()


def upload(client, pid, name, content):
    r = client.post(f'/api/projects/{pid}/files', files={'file': (name, content)})
    assert r.status_code == 201, r.text
    return r.json()['file_id']


@pytest.mark.parametrize('units,expected', [(4, 5), (6, 5000), (0, None)])
def test_dxf_real_parser_units_original_and_history(client, units, expected):
    pid = create_project(client)['project_id']; base=f'/api/projects/{pid}/cad-inspections'
    content = dxf_bytes(units)
    fid = upload(client, pid, 'independent.dxf', content)
    r = client.post(base, json={'file_id':fid})
    assert r.status_code == 201, r.text
    record = r.json(); data = record['result']
    assert data['counts'] == {'LINE':1,'TEXT':1}
    assert data['objects'][0]['length_m'] == expected
    assert record['source']['hash'] == hashlib.sha256(content).hexdigest()
    _, original = client.app.state.domain.file_record(pid, fid)
    assert original.read_bytes() == content
    other = create_project(client)['project_id']
    assert client.post(f'/api/projects/{other}/cad-inspections', json={'file_id':fid}).status_code == 409
    assert client.get(base+'/'+record['cad_id']).json()['result'] == data
    _, path = client.app.state.domain.file_record(pid, fid)
    path.write_bytes(b'corrupt original in isolated test')
    assert client.get(base+'/'+record['cad_id']).json()['result'] is None
    assert client.post(base, json={'file_id':fid}).status_code == 409


def test_ifc_real_parser_classification_properties_container(client):
    pid = create_project(client)['project_id']
    fid = upload(client, pid, 'independent.ifc', ifc_bytes())
    r = client.post(f'/api/projects/{pid}/cad-inspections', json={'file_id':fid})
    assert r.status_code == 201, r.text
    result = r.json()['result']
    assert result['counts'] == {'IfcWall':1,'IfcDoor':1,'IfcBuildingStorey':1}
    assert result['length_scale_to_m'] == .001
    wall = next(x for x in result['objects'] if x['type']=='IfcWall')
    floor = next(x for x in result['objects'] if x['type']=='IfcBuildingStorey')
    assert wall['container_id'] == floor['id']
    assert wall['properties'][0]['value'] == '2h'
    assert len(result['issues']) == 3  # metadata extraction never invents placement


@pytest.mark.parametrize('name,content', [('bad.dxf', b'not a drawing'), ('bad.ifc', b'ISO-10303-21; broken'), ('duplicate.ifc', ifc_bytes(True))])
def test_corrupt_and_duplicate_files_rejected_without_success(client, name, content):
    pid = create_project(client)['project_id']
    fid = upload(client, pid, name, content)
    base = f'/api/projects/{pid}/cad-inspections'
    assert client.post(base, json={'file_id':fid}).status_code == 409
    assert client.get(base).json() == []


def test_timeout_releases_capacity_and_no_anonymous_read(client, monkeypatch):
    pid = create_project(client)['project_id']; fid = upload(client, pid, 'test.dxf', dxf_bytes())
    service = Cad(client.app.state.domain)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-never-forward')
    def timeout(*a, **k):
        assert 'DEEPSEEK_API_KEY' not in k['env']
        raise subprocess.TimeoutExpired('parser',30)
    monkeypatch.setattr(subprocess, 'run', timeout)
    for _ in range(3):
        with pytest.raises(core.ValidationError, match='timed out'):
            service.inspect(pid, Inspection(file_id=fid))
    client.cookies.clear()
    assert client.get(f'/api/projects/{pid}/cad-inspections').status_code == 401
