import asyncio
from backend.traffic import Admission


def test_concurrency_rejects_excess_and_releases_after_failure():
    async def run():
        gate=asyncio.Event();statuses=[]
        async def app(scope,receive,send):
            await gate.wait()
            raise RuntimeError('controlled downstream failure')
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):
            if message['type']=='http.response.start':statuses.append(message['status'])
        service=Admission(app,concurrency=1)
        first=asyncio.create_task(service({'type':'http','path':'/api/projects'},receive,send))
        await asyncio.sleep(0)
        await service({'type':'http','path':'/api/projects'},receive,send)
        assert statuses==[429] and service.active==1
        gate.set()
        try:await first
        except RuntimeError:pass
        assert service.active==0
    asyncio.run(run())


def test_upload_limit_applies_before_body_is_read():
    async def run():
        gate=asyncio.Event();statuses=[];reads=0
        async def app(scope,receive,send):
            await receive();await gate.wait()
        async def receive():
            nonlocal reads
            reads+=1;return {'type':'http.request','body':b'controlled'}
        async def send(message):
            if message['type']=='http.response.start':statuses.append(message['status'])
        service=Admission(app,upload_concurrency=1)
        scope={'type':'http','path':'/api/projects/p/files','method':'POST'}
        first=asyncio.create_task(service(scope,receive,send));await asyncio.sleep(0)
        await service(scope,receive,send)
        assert reads==1 and statuses==[429]
        gate.set();await first
        assert service.active==0 and service.upload_active==0
    asyncio.run(run())
