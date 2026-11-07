"""Source-derived material transport legs; explicit distance and additional mass."""
from decimal import Decimal, localcontext

from pydantic import Field, StrictFloat, StrictInt, model_validator

from . import core, lifecycle
from .schema import Contract


class TransportLeg(Contract):
    leg_id: str = Field(min_length=1, max_length=60, pattern=r'^[a-zA-Z0-9_-]+$')
    name: str = Field(min_length=2, max_length=160)
    layer_ids: list[StrictInt] = Field(min_length=1, max_length=32)
    purchase_fraction: StrictFloat | None = Field(default=None, gt=0, le=1)
    fraction_source: str = Field(min_length=5, max_length=1000)
    distance_km: StrictFloat | None = Field(default=None, ge=0, le=1000000)
    distance_source: str = Field(min_length=5, max_length=2000)
    additional_mass_kg: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    additional_mass_source: str = Field(min_length=5, max_length=1000)
    factor: lifecycle.EmissionFactor
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def coherent(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('Duplicate transport source evidence')
        if len(set(self.layer_ids)) != len(self.layer_ids) or any(i <= 0 for i in self.layer_ids):
            raise ValueError('Transport layers must be distinct positive IDs')
        if self.factor.stage != 'transport' or self.factor.denominator != 'tkm':
            raise ValueError('Transport leg requires a transport factor in kgCO2e/tkm')
        return self


def derive(legs, mappings, derivations, takeoff):
    materials = {r.layer_id:r for r in mappings}
    volumes = {r['layer_id']:r for r in derivations}
    activities, receipts = [], []
    with localcontext() as ctx:
        ctx.prec = 80
        for leg in legs:
            if not set(leg.layer_ids) <= materials.keys():
                raise core.ValidationError('Transport leg contains an excluded or unknown material layer')
            parts, missing = [], []
            for layer_id in leg.layer_ids:
                mapping, quantity = materials[layer_id], volumes[layer_id]['purchase_volume_m3']
                mass = None if quantity is None or mapping.density_kg_m3 is None else Decimal(quantity)*Decimal(str(mapping.density_kg_m3))
                if mass is None:missing.append('layer_'+str(layer_id)+':purchase_mass')
                parts.append({'layer_id':layer_id,'purchase_volume_m3':quantity,
                    'density_kg_m3':mapping.density_kg_m3,'density_source':mapping.density_source,
                    'purchase_mass_kg':None if mass is None else str(mass)})
            for key in ['purchase_fraction','distance_km','additional_mass_kg']:
                if getattr(leg,key) is None:missing.append(key)
            total = None if any(p['purchase_mass_kg'] is None for p in parts) else sum((Decimal(p['purchase_mass_kg']) for p in parts),Decimal(0))
            shipped = None if missing else total*Decimal(str(leg.purchase_fraction))+Decimal(str(leg.additional_mass_kg))
            tkm = None if shipped is None else shipped/Decimal(1000)*Decimal(str(leg.distance_km))
            key = 'transport_'+leg.leg_id
            activities.append(lifecycle.Activity(activity_id=key,name=leg.name,stage='transport',
                quantity=None if tkm is None else float(tkm),unit='tkm',period='whole_period',
                source=takeoff['takeoff_id']+' / '+takeoff['hash']+' / leg '+leg.leg_id,factor=leg.factor))
            receipts.append({'activity_id':key,'leg_id':leg.leg_id,'name':leg.name,'layers':parts,
                'purchase_mass_kg':None if total is None else str(total),'purchase_fraction':leg.purchase_fraction,
                'additional_mass_kg':leg.additional_mass_kg,'shipped_mass_kg':None if shipped is None else str(shipped),
                'distance_km':leg.distance_km,'quantity_tkm':None if tkm is None else str(tkm),'missing':missing,
                'formula':'(sum(purchase_volume_m3 * density_kg_m3) * purchase_fraction + additional_mass_kg) / 1000 * distance_km',
                'boundary':'Selected purchased materials on this leg; additional packaging/pallet mass declared separately. Routing and allocation are user-declared.'})
    return activities, receipts
