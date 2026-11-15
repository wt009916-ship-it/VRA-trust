"""Selected-page OCR with immutable source linkage; candidates are never citations."""
import shutil
from pathlib import Path
from pydantic import Field, StrictInt
from . import core, parser_runtime
from .domain import identifier
from .schema import Contract
from .drawings import Drawings, DrawingProcessing, parser_hash as drawing_hash


class PageOCR(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    page: StrictInt = Field(ge=1, le=500)


def engine_hash():
    from .standards import parser_hash
    return core.hash_json({'extractor':parser_hash(),'ocr':drawing_hash(),
                          'bridge':core.sha(Path(__file__))})


class StandardOCR:
    def __init__(self,domain): self.domain,self.store=domain,domain.store

    def save(self,pid,body):
        source,path=self.domain.file_record(pid,body.file_id)
        if path.suffix.lower()!='.pdf' or source['size']>20*1024**2:
            raise core.ValidationError('Provide PDF up to 20 MiB')
        if len(self.store.list('normocr',pid))>=100:
            raise core.ValidationError('Project standard OCR limit is 100 pages')
        if not Drawings.capacity.acquire(False):
            raise core.ValidationError('OCR busy; retry after current task')
        try:
            before=engine_hash()
            # Keep both subprocesses isolated. The first copies ONLY the selected
            # page; the existing drawing limits are unchanged (10 MiB / 12M px).
            with parser_runtime.run('standards',path,body.page,options={'operation':'select_page'}) as selected:
                page=selected['work']/'selected.pdf';selection=core.read_json(selected['work']/'result.json')
                if not page.is_file() or not 0<page.stat().st_size<=10*1024**2 or core.sha(page)!=selection['selected_sha256']:
                    raise core.ValidationError('Selected page exceeded budget or changed')
                with parser_runtime.run('drawing',page,1,options=DrawingProcessing().model_dump()) as scope:
                    out,preview=scope['work']/'result.json',scope['work']/'preview.png'
                    if not out.is_file() or out.stat().st_size>2*1024**2 or not preview.is_file() or preview.stat().st_size>40*1024**2:
                        raise core.ValidationError('OCR output budget exceeded')
                    result=core.read_json(out)
                    self.domain.file_record(pid,body.file_id)
                    if engine_hash()!=before or core.sha(preview)!=result['preview_sha256']:
                        raise core.ValidationError('OCR source or parser changed')
                    oid=identifier('normocr');target=self.store.root/'standard-ocr'/oid
                    target.mkdir(parents=True,exist_ok=False)
                    shutil.copyfile(preview,target/'preview.png')
                    # Retain the page bytes that were actually rendered, not a
                    # later reconstruction silently replacing historical evidence.
                    shutil.copyfile(page,target/'selected.pdf')
                    result['original_pdf_page']=body.page
                    result['resource_limits']=scope['resource_limits']
                    obj={'normocr_id':oid,'project_id':pid,'input':body.model_dump(),
                         'source':source,'engine_hash':before,'created_at':core.now(),
                         'selection':selection,'selection_limits':selected['resource_limits'],
                         'result':result,'artifacts':{
                             'preview.png':{'path':(target/'preview.png').relative_to(self.store.root).as_posix(),'hash':result['preview_sha256']},
                             'selected.pdf':{'path':(target/'selected.pdf').relative_to(self.store.root).as_posix(),'hash':selection['selected_sha256']}}}
            obj['hash']=core.hash_json(obj);self.store.put('normocr',obj)
            return self.view(pid,oid)
        finally: Drawings.capacity.release()

    def view(self,pid,oid):
        obj=self.store.get('normocr',oid)
        if obj['project_id']!=pid: raise core.ValidationError('Cross-project OCR rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'revision','hash'}})!=obj['hash']:
            raise core.ValidationError('OCR record integrity failed')
        stale=False
        try:
            self.domain.file_record(pid,obj['input']['file_id'])
            stale=engine_hash()!=obj['engine_hash']
            for a in obj['artifacts'].values():
                stale=stale or core.sha(core.relative_file(self.store.root,a['path']))!=a['hash']
        except (ValueError,KeyError,OSError,ImportError): stale=True
        return {**obj,'status':'stale' if stale else 'review_required',
                'result':None if stale else obj['result']}

    def artifact(self,pid,oid,name):
        obj=self.view(pid,oid)
        if obj['status']=='stale' or name not in obj['artifacts']:
            raise core.ValidationError('Current OCR artifact unavailable')
        return core.relative_file(self.store.root,obj['artifacts'][name]['path'])


def register(app,domain):
    from fastapi.responses import FileResponse
    service=StandardOCR(domain)
    @app.post('/api/projects/{project_id}/standard-ocr',status_code=201)
    def create(project_id:str,body:PageOCR): return service.save(project_id,body)
    @app.get('/api/projects/{project_id}/standard-ocr/{normocr_id}')
    def view(project_id:str,normocr_id:str): return service.view(project_id,normocr_id)
    @app.get('/api/projects/{project_id}/standard-ocr/{normocr_id}/{name}')
    def artifact(project_id:str,normocr_id:str,name:str):
        return FileResponse(service.artifact(project_id,normocr_id,name),
            media_type='image/png' if name=='preview.png' else 'application/pdf',
            headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
