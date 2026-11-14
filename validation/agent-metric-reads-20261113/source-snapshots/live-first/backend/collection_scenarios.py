"""Two alternatives bound to deduplicated IFC material entities, not wall-layer IDs."""
from fastapi.responses import HTMLResponse
from pydantic import Field, StrictInt, model_validator
from .schema import Contract
from .material_transport import TransportInput
from .material_scenarios import MaterialMapping, ScenarioActivity, ScenarioContext, MaterialScenarios, validate_scenario, report


class CollectionMaterial(MaterialMapping):
    source_material_id: StrictInt = Field(gt=0)


class MaterialExclusion(Contract):
    source_material_id: StrictInt = Field(gt=0)
    reason: str = Field(min_length=5, max_length=1000)


class MaterialTransportLeg(TransportInput):
    material_ids: list[StrictInt] = Field(min_length=1, max_length=256)

    @property
    def selected_ids(self):
        return self.material_ids


class MaterialAlternative(Contract):
    name: str = Field(min_length=1, max_length=160)
    materials: list[CollectionMaterial] = Field(min_length=1, max_length=256)
    other_activities: list[ScenarioActivity] = Field(default_factory=list, max_length=300)
    transport_legs: list[MaterialTransportLeg] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique(self):
        if len({r.source_material_id for r in self.materials}) != len(self.materials):
            raise ValueError('Duplicate source material entity; double counting rejected')
        if len({r.leg_id for r in self.transport_legs}) != len(self.transport_legs):
            raise ValueError('Duplicate transport leg ID')
        if any(a.stage == 'production' for a in self.other_activities):
            raise ValueError('Production must be derived from source material mappings')
        return self


class CollectionScenarioRequest(ScenarioContext):
    materialset_id: str = Field(pattern=r'^materialset_[a-f0-9]{32}$')
    excluded_materials: list[MaterialExclusion] = Field(default_factory=list, max_length=255)
    alternatives: list[MaterialAlternative] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def coherent(self):
        return validate_scenario(self, 'materials', 'source_material_id', 'excluded_materials')


class CollectionScenarios(MaterialScenarios):
    source_kind = 'collection'
    source_id_field = 'materialset_id'
    source_hash_field = 'materialset_hash'
    record_kind = 'collectionscenario'
    mappings_field = 'materials'


def register(app, collections):
    service = CollectionScenarios(collections)
    app.state.collection_scenarios = service

    @app.post('/api/projects/{project_id}/collection-scenarios', status_code=201)
    def create(project_id: str, body: CollectionScenarioRequest):
        return service.create(project_id, body)

    @app.get('/api/projects/{project_id}/collection-scenarios')
    def history(project_id: str):
        return [{'collectionscenario_id':r['collectionscenario_id'], 'created_at':r['created_at'],
                 'names':[a['name'] for a in r['input']['alternatives']]} for r in service.store.list('collectionscenario', project_id)]

    @app.get('/api/projects/{project_id}/collection-scenarios/{collectionscenario_id}')
    def current(project_id: str, collectionscenario_id: str):
        return service.view(project_id, collectionscenario_id)

    @app.get('/api/projects/{project_id}/collection-scenarios/{collectionscenario_id}/report.html', response_class=HTMLResponse)
    def html_report(project_id: str, collectionscenario_id: str):
        return report(service.view(project_id, collectionscenario_id))
