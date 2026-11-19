"""Actual network gameplay: move actor -> harvest -> move -> donate -> verify board."""
import asyncio,json,sys,requests,websockets

BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765'

async def main():
    s=requests.Session();r=s.post(BASE+'/api/guest',json={'nickname':'E2E Builder'},timeout=5);r.raise_for_status();p=r.json()['player']
    w=BASE.replace('http://','ws://').replace('https://','wss://')+'/ws'
    async with websockets.connect(w,additional_headers={'Cookie':'agentopia_sid='+s.cookies['agentopia_sid']}) as ws:
        while json.loads(await ws.recv()).get('type')!='snapshot':pass
        await ws.send(json.dumps({'type':'input','dx':-1,'dy':0}))
        await asyncio.sleep(1.55)
        await ws.send(json.dumps({'type':'input','dx':0,'dy':0}))
        await asyncio.sleep(.15)
        collected=s.post(BASE+'/api/gather',json={'node_id':'oak'},timeout=5)
        assert collected.status_code==200,(collected.status_code,collected.text)
        assert collected.json()['player']['wood']==1
        await ws.send(json.dumps({'type':'input','dx':1,'dy':0}))
        await asyncio.sleep(4.3)
        await ws.send(json.dumps({'type':'input','dx':0,'dy':0}))
        await asyncio.sleep(.1)
        built=s.post(BASE+'/api/build',json={'material':'wood','amount':1},timeout=5)
        assert built.status_code==200,(built.status_code,built.text)
        assert built.json()['player']['wood']==0
        assert built.json()['world']['bridge']['progress']>=1
        assert any(x['id']==p['id'] and x['contributed']==1 for x in s.get(BASE+'/api/leaderboard',timeout=5).json()['players'])
        print('PASS: real browser-independent API/WebSocket gameplay: walk -> harvest -> walk -> build -> leaderboard.')

if __name__=='__main__':asyncio.run(main())
