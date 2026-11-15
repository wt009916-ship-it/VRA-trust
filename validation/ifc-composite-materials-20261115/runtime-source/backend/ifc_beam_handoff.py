"""Source-bound IFC section extraction and explicit reviewed engineering handoff."""
from pathlib import Path
from typing import Literal

from fastapi import Request
from pydantic import Field, StrictBool, StrictInt

from . import core, parser_runtime
from .cad import Cad, parser_version
from .calculation_provenance import persist, validity
from .domain import identifier
from .engineering import BeamInput, Engineering, SectionProfile
from .schema import Contract


def version():
    return core.hash_json({'cad': parser_version(), 'handoff':core.sha(Path(__file__)),
        'profiles':core.sha(Path(__file__).with_name('ifc_beam_profiles.py')),
        'sections':core.sha(Path(__file__).with_name('beam_sections.py'))})


class ProfileRequest(Contract):
    cad_id: str = Field(pattern=r'^cad_[a-f0-9]{32}$')
    product_id: StrictInt = Field(gt=0, le=2147483647)


class ReviewedBeam(Contract):
    expected_profile_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    bending_axis: Literal['x', 'y']
    geometry_reviewed: StrictBool
    review_basis: str = Field(min_length=20, max_length=2000)
    analysis: BeamInput


class BeamProfiles:
    def __init__(self, cad):
        self.cad, self.domain, self.store = cad, cad.domain, cad.store

    def create(self, pid, body):
        project = self.store.get('project', pid)
        source = self.cad.view(pid, body.cad_id)
        if source['status'] != 'parsed' or source['result']['format'] != 'IFC':
            raise core.ValidationError('A current IFC inspection is required')
        matches = [row for row in source['result']['objects'] if row['id'] == body.product_id]
        if len(matches) != 1 or matches[0]['type'] not in {'IfcBeam', 'IfcBeamStandardCase'}:
            raise core.ValidationError('Select one IFC beam in this inspection')
        if not self.cad.capacity.acquire(False):
            raise core.ValidationError('File parsers busy; retry later')
        try:
            original, path = self.domain.file_record(pid, source['source']['file_id'])
            before = version()
            with parser_runtime.run('cad', path, options={'operation':'ifc_beam_profile', 'product_id':body.product_id}) as scope:
                target = scope['work']/'result.json'
                if not target.exists() or target.stat().st_size > 128*1024:
                    raise core.ValidationError('IFC profile output unavailable or too large')
                result = core.read_json(target)
                if 'error' in result or result.get('status') not in {'extracted','unsupported'} or result.get('product_id') != body.product_id:
                    raise core.ValidationError('IFC profile extraction rejected; original preserved')
                if result['status'] == 'extracted':
                    SectionProfile(**result['section_profile'], bending_axis='x')
                result['resource_limits'] = scope['resource_limits']
            obj = {'beamprofile_id':identifier('beamprofile'), 'project_id':pid,
                   'project_revision':project['revision'], 'created_at':core.now(),
                   'cad_id':body.cad_id, 'inspection_hash':source['hash'],
                   'file_snapshot':original, 'calculator_hash':before, 'result':result}
            obj['hash'] = core.hash_json(obj)
            def check():
                current = self.cad.view(pid, body.cad_id)
                if current['status'] != 'parsed' or current['hash'] != source['hash'] or version() != before:
                    raise core.ValidationError('IFC sources changed during extraction')
            persist(self.domain, 'beamprofile', obj, pre_insert_check=check)
            return self.view(pid, obj['beamprofile_id'])
        finally:
            self.cad.capacity.release()

    def view(self, pid, ident):
        obj = self.store.get('beamprofile', ident)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project IFC profile rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('IFC profile integrity failed')
        provenance = validity(self.domain, obj, version())
        reasons = provenance['stale_reasons']
        try:
            source = self.cad.view(pid, obj['cad_id'])
            if source['status'] != 'parsed' or source['hash'] != obj['inspection_hash']:
                reasons.append('cad_inspection_changed')
        except (ValueError, OSError, KeyError):
            reasons.append('cad_inspection_unavailable')
        return {**obj, **provenance, 'status':'stale' if reasons else obj['result']['status'],
                'result':None if reasons else obj['result'], 'assessment':'MODEL_PROFILE_NOT_STRUCTURAL_APPROVAL'}

    def handoff(self, pid, ident, body, actor):
        record = self.view(pid, ident)
        if record['status'] != 'extracted' or record['hash'] != body.expected_profile_hash:
            raise core.ValidationError('Review the current IFC profile before creating an analysis')
        if body.geometry_reviewed is not True or not body.review_basis.strip():
            raise core.ValidationError('An explicit geometry and axis review is required')
        given = body.analysis
        if given.section_profile is not None or given.width is not None or given.depth is not None:
            raise core.ValidationError('Reviewed handoff takes section geometry only from the bound IFC profile')
        profile = {**record['result']['section_profile'], 'bending_axis':body.bending_axis}
        payload = given.model_dump()
        payload.update(section_profile=profile)
        analysis = BeamInput(**payload)
        snapshot = {'beamprofile_id':ident, 'hash':record['hash'], 'file_snapshot':record['file_snapshot'],
                    'cad_id':record['cad_id'], 'product_id':record['result']['product_id'],
                    'bending_axis':body.bending_axis, 'review_basis':body.review_basis,
                    'actor_user_id':actor, 'source_kind':'MODEL_GEOMETRY_NOT_MEASURED'}
        return Engineering(self.domain).save(pid, analysis, ifc_binding=snapshot)


def validate_snapshot(domain, pid, snapshot):
    current = BeamProfiles(Cad(domain)).view(pid, snapshot['beamprofile_id'])
    if current['status'] != 'extracted' or current['hash'] != snapshot['hash'] or current['file_snapshot'] != snapshot['file_snapshot']:
        raise core.ValidationError('IFC profile source is no longer current')


def register(app, cad):
    profiles = BeamProfiles(cad)

    @app.get('/api/projects/{project_id}/ifc-beam-profile-inputs')
    def inputs(project_id: str):
        records = [r for r in profiles.store.list('cad',project_id) if r['source']['name'].lower().endswith('.ifc')]
        return {'items':[{'cad_id':r['cad_id'], 'name':r['source']['name'], 'created_at':r['created_at']} for r in records[:100]],
                'truncated':len(records)>100, 'current_state':'check_selected_record'}

    @app.post('/api/projects/{project_id}/ifc-beam-profiles', status_code=201)
    def create(project_id: str, body: ProfileRequest):
        return profiles.create(project_id, body)

    @app.get('/api/projects/{project_id}/ifc-beam-profiles')
    def listing(project_id: str):
        return [profiles.view(project_id,r['beamprofile_id']) for r in profiles.store.list('beamprofile', project_id)]

    @app.get('/api/projects/{project_id}/ifc-beam-profiles/{profile_id}')
    def get(project_id: str, profile_id: str):
        return profiles.view(project_id, profile_id)

    @app.post('/api/projects/{project_id}/ifc-beam-profiles/{profile_id}/analyses', status_code=201)
    def handoff(project_id: str, profile_id: str, body: ReviewedBeam, request: Request):
        return profiles.handoff(project_id, profile_id, body, request.state.user['id'])
