"""30-real-socket integration load smoke (not a substitute for production load test)."""
import asyncio,json,random,requests,websockets,time,sys
BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765'
async def run():
    players=[]
    for idx in range(30):
        s=requests.Session()
        r=s.post(BASE+'/api/guest',json={'nickname':f'LoadPlayer{idx:02d}'},timeout=7)
        r.raise_for_status()
        players.append((s.cookies['agentopia_sid'],r.json()['player']['id']))
    ready=asyncio.Event();active=0;counts=[];errors=[]
    async def worker(idx,cookie,pid):
        nonlocal active
        try:
            uri=BASE.replace('http://','ws://').replace('https://','wss://')+'/ws'
            async with websockets.connect(uri,additional_headers={'Cookie':'agentopia_sid='+cookie},max_size=2**20) as ws:
                active+=1
                if active==30:ready.set()
                await ready.wait()
                await ws.send(json.dumps({'type':'input','dx':(idx%3)-1,'dy':0}))
                until=time.monotonic()+1.0
                seen=0
                while time.monotonic()<until:
                    event=json.loads(await asyncio.wait_for(ws.recv(),timeout=3))
                    if event.get('type')=='snapshot':
                        seen+=1;assert len(event['players'])>=28
                counts.append(seen)
        except Exception as exc:errors.append((idx,repr(exc)))
    start=time.monotonic()
    await asyncio.wait_for(asyncio.gather(*(worker(i,cookie,pid) for i,(cookie,pid) in enumerate(players))),timeout=20)
    elapsed=time.monotonic()-start
    assert not errors,errors
    assert len(counts)==30,len(counts)
    print(f'PASS: 30 concurrent real WebSockets; all clients received snapshots; samples min={min(counts)}, max={max(counts)}; walltime {elapsed:.2f}s')
if __name__=='__main__':asyncio.run(run())
