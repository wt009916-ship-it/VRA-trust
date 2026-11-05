"""Project-protected OCR candidates and append-only human transcription reviews."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt, model_validator
from . import core
from .domain import identifier
from .drawing_models import model_paths, MODELS
from .schema import Contract


class DrawingInput(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    page: StrictInt = Field(default=1, ge=1, le=200)


class DrawingReview(Contract):
    expected_revision: StrictInt = Field(ge=1)
    candidate_id: str = Field(pattern=r'^text_[1-9][0-9]{0,2}$')
    decision: Literal['confirmed','corrected','rejected','unreadable']
    corrected_text: str | None = Field(default=None,min_length=1,max_length=2000)
    basis: str = Field(min_length=10,max_length=2000)

    @model_validator(mode='after')
    def correction(self):
        if (self.decision=='corrected') != (self.corrected_text is not None):
            raise ValueError('Only corrected decisions require corrected_text')
        return self


def parser_hash():
    model_paths()
    return core.hash_json({'worker':core.sha(Path(__file__).with_name('drawing_worker.py')),
                          'model_contract':core.sha(Path(__file__).with_name('drawing_models.py')),
                          'models':MODELS,'versions':{p:version(p) for p in ('rapidocr','onnxruntime','Pillow','pypdfium2','numpy','opencv-python-headless')}})


class Drawings:
    capacity = threading.BoundedSemaphore(1)

    def __init__(self,domain):
        self.domain,self.store=domain,domain.store

    def save(self,pid,body):
        source,path=self.domain.file_record(pid,body.file_id)
        if path.suffix.lower() not in {'.png','.jpg','.jpeg','.pdf'} or source['size']>10*1024*1024:
            raise core.ValidationError('OCR accepts PNG/JPEG/PDF up to 10 MiB')
        if len(self.store.list('drawing',pid))>=50:
            raise core.ValidationError('Project OCR record limit is 50')
        if not self.capacity.acquire(False):
            raise core.ValidationError('OCR busy; retry after current task')
        try:
            try:
                before=parser_hash()
            except (ValueError,OSError,PackageNotFoundError) as exc:
                raise core.ValidationError('OCR models unavailable or modified') from exc
            with tempfile.TemporaryDirectory(prefix='vra-ocr-') as tmp:
                out,preview=Path(tmp)/'result.json',Path(tmp)/'preview.png'
                env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL'}}
                env.update(USERPROFILE=tmp,XDG_CONFIG_HOME=tmp,OMP_NUM_THREADS='2')
                try:
                    cp=subprocess.run([sys.executable,str(Path(__file__).with_name('drawing_worker.py')),str(path),str(out),str(preview),str(body.page)],
                                      cwd=tmp,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                      env=env,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except subprocess.TimeoutExpired:
                    raise core.ValidationError('OCR timed out; original preserved') from None
                if cp.returncode or not out.is_file() or out.stat().st_size>2*1024*1024 or not preview.is_file() or preview.stat().st_size>40*1024*1024:
                    raise core.ValidationError('OCR rejected or exceeded limits; original preserved')
                result=core.read_json(out)
                self.domain.file_record(pid,body.file_id)
                if parser_hash()!=before or core.sha(preview)!=result['preview_sha256']:
                    raise core.ValidationError('OCR inputs or parser changed during processing')
                did=identifier('drawing')
                target=self.store.root/'drawings'/did
                target.mkdir(parents=True,exist_ok=False)
                shutil.copyfile(preview,target/'preview.png')
            obj={'drawing_id':did,'project_id':pid,'created_at':core.now(),'source':source,'input':body.model_dump(),
                 'parser_hash':before,'result':result,'reviews':{},'last_review':None,
                 'preview_path':(target/'preview.png').relative_to(self.store.root).as_posix()}
            obj['hash']=core.hash_json(obj)
            self.store.put('drawing',obj)
            return self.view(pid,did)
        finally:
            self.capacity.release()

    def _record(self,pid,did):
        obj=self.store.get('drawing',did)
        if obj['project_id']!=pid:
            raise core.ValidationError('Cross-project drawing rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'revision','hash'}})!=obj['hash']:
            raise core.ValidationError('Drawing record integrity failed')
        return obj

    def view(self,pid,did):
        obj=self._record(pid,did)
        stale=False
        try:
            self.domain.file_record(pid,obj['source']['file_id'])
            preview=core.relative_file(self.store.root,obj['preview_path'])
            stale=parser_hash()!=obj['parser_hash'] or core.sha(preview)!=obj['result']['preview_sha256']
        except (OSError,ValueError,KeyError,PackageNotFoundError):
            stale=True
        return {**obj,'status':'stale' if stale else 'review_required',
                'result':None if stale else obj['result'],'reviews':None if stale else obj['reviews'],
                'assessment':'OCR_AND_HUMAN_TRANSCRIPTION_NOT_ENGINEERING_APPROVAL'}

    def preview(self,pid,did):
        obj=self.view(pid,did)
        if obj['status']=='stale':
            raise core.ValidationError('Stale preview; create a new OCR record')
        return core.relative_file(self.store.root,obj['preview_path'])

    def review(self,pid,did,body,reviewer):
        current=self.view(pid,did)
        if current['status']=='stale':
            raise core.ValidationError('Cannot review stale OCR')
        obj=self._record(pid,did)
        candidate=next((x for x in obj['result']['candidates'] if x['candidate_id']==body.candidate_id),None)
        if candidate is None:
            raise core.ValidationError('OCR candidate does not exist; cannot invent a missing label')
        action={**body.model_dump(exclude={'expected_revision'}),'reviewer_id':reviewer,'reviewed_at':core.now(),
                'original_text':candidate['text'],'source_kind':'HUMAN_TRANSCRIPTION',
                'effective_text':candidate['text'] if body.decision=='confirmed' else body.corrected_text if body.decision=='corrected' else None}
        obj['reviews']={**obj['reviews'],body.candidate_id:action}
        obj['last_review']=action
        obj.pop('revision',None);obj.pop('hash',None)
        obj['hash']=core.hash_json(obj)
        self.store.put('drawing',obj,expected=body.expected_revision)
        return self.view(pid,did)

    def history(self,pid,did):
        self._record(pid,did)
        return [{'revision':r['revision'],'hash':r['hash'],'last_review':r['last_review']} for r in self.store.history('drawing',did)]
