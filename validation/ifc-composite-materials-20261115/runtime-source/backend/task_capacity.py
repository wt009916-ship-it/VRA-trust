"""Persistent admission limits and failure-safe background task ownership."""
import os
import re
import threading
from dataclasses import dataclass

from . import core


class CapacityError(core.ValidationError):
    pass


@dataclass(frozen=True)
class TaskLimits:
    runs: int = 16
    project_runs: int = 4
    agent: int = 2
    search: int = 1

    @classmethod
    def from_env(cls):
        values={}
        for key,name in [('runs','VRA_ACTIVE_RUNS'),('project_runs','VRA_PROJECT_ACTIVE_RUNS'),('agent','VRA_ACTIVE_AGENTS'),('search','VRA_ACTIVE_SEARCHES')]:
            if name in os.environ:
                value=os.environ[name]
                if not re.fullmatch('[1-9][0-9]{0,2}',value) or int(value)>256:
                    raise ValueError(name+' must be an integer from 1 to 256')
                values[key]=int(value)
        return cls(**values)


def launch(service, kind, record, args=(), *, background=True):
    """The launcher owns each acquired slot, including pre-execute failures."""
    domain=service.domain
    def fail_record(message):
        current=service.store.get(kind,record[kind+'_id'])
        if current['status']=='running':
            fields={'status':'failed','error':message,'finished_at':core.now()}
            if kind=='agent':fields['answer']=None
            else:fields['stability_status']='SIMULATION_FAILED'
            service.store.put(kind,{**current,**fields},current['revision'])
    def run():
        try:
            service.execute(record,*args)
        except Exception:
            try:fail_record('Task execution/finalization interrupted; retry explicitly')
            except Exception:pass  # persist no invented success; startup recovery retries
            if not background:raise
        finally:
            service.capacity.release()
            with domain.task_lock:domain.tasks.discard(threading.current_thread())
    with domain.task_lock:
        if domain.stop.is_set():raise CapacityError('服务正在关闭，未接受新任务')
        if not service.capacity.acquire(blocking=False):raise CapacityError('任务容量已满，请等待当前任务完成')
        try:
            record=service.store.add_active_record(kind,record)
        except Exception:
            service.capacity.release();raise
        if background:
            thread=None
            try:
                thread=threading.Thread(target=run,daemon=True,name='vra-'+kind)
                domain.tasks.add(thread)
                thread.start()
            except Exception:
                domain.tasks.discard(thread)
                try:fail_record('Task thread could not start; no work executed')
                finally:service.capacity.release()
                raise
    if not background:run()
    return service.store.get(kind,record[kind+'_id'])
