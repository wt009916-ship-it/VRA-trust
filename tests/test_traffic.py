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
