from pathlib import Path
p=Path('backend/cad.py');s=p.read_text(encoding='utf-8').replace('from pydantic import Field','from typing import Annotated\nfrom pydantic import Field, model_validator')
marker='\n\ndef parser_version():'
body='''

class CurrentStates(Contract):
    cad_ids: list[Annotated[str, Field(pattern=r'^cad_[a-f0-9]{32}$')]] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_ids(self):
        if len(set(self.cad_ids)) != len(self.cad_ids):
            raise ValueError('Duplicate CAD records in current-state request')
        return self
'''
s=s.replace(marker,body+marker)
start=s.index('    def view(self, pid, cid):')
s=s[:start]+'''    def _record(self, pid, cid):
        obj = self.store.get('cad', cid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project CAD record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Inspection record integrity failed')
        return obj

    def _state(self, pid, obj, current_parser, source_cache):
        reasons = []
        if current_parser is None:
            reasons.append('parser_unavailable')
        elif obj['parser_hash'] != current_parser:
            reasons.append('parser_changed')
        fid = obj['source']['file_id']
        if fid not in source_cache:
            try:
                current, _ = self.domain.file_record(pid, fid)
                source_cache[fid] = current['hash']
            except (OSError, ValueError, KeyError):
                source_cache[fid] = None
        if source_cache[fid] is None:
            reasons.append('source_unavailable')
        elif source_cache[fid] != obj['source']['hash']:
            reasons.append('source_binding_changed')
        status = 'unverified' if current_parser is None else ('stale' if reasons else 'parsed')
        return {'cad_id': obj['cad_id'], 'status': status, 'reasons': reasons,
                'inspection_hash': obj['hash'], 'source_hash': obj['source']['hash'],
                'parser_hash': obj['parser_hash'], 'current_parser_hash': current_parser}

    @staticmethod
    def _current_parser():
        try:
            return parser_version()
        except (OSError, ValueError, ImportError):
            return None

    def current_states(self, pid, body):
        # Validate every requested record's ownership/integrity before checking
        # source data; no partial cross-project replies and no record mutations.
        objects = [self._record(pid, cid) for cid in body.cad_ids]
        current_parser, source_cache = self._current_parser(), {}
        states = [self._state(pid, obj, current_parser, source_cache) for obj in objects]
        return {'checked_at': core.now(), 'states': states, 'poll_after_ms': 5000}

    def view(self, pid, cid):
        obj = self._record(pid, cid)
        state = self._state(pid, obj, self._current_parser(), {})
        return {**obj, 'status': state['status'], 'stale_reasons': state['reasons'],
                'checked_at': core.now(), 'result': obj['result'] if state['status'] == 'parsed' else None,
                'assessment': 'READ_ONLY_EXTRACTION_NOT_ENGINEERING_APPROVAL'}
'''
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('backend/extensions.py');s=p.read_text(encoding='utf-8')
a=next(line for line in s.splitlines() if line.startswith('from .cad import'))
s=s.replace(a,a+', CurrentStates')
marker="    @app.post('/api/projects/{project_id}/cad-inspections', status_code=201)"
s=s.replace(marker,"""    @app.post('/api/projects/{project_id}/cad-current-states')
    def cad_current_states(project_id: str, body: CurrentStates):
        return cad.current_states(project_id, body)

"""+marker)
p.write_text(s,encoding='utf-8',newline='\n')
