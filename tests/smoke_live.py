"""Run with live server: python tests/smoke_live.py [url].
Verifies two actual WebSocket clients and authoritative movement over TCP.
"""
import asyncio,json,sys,requests,websockets

BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765'

def guest(name):
    s=requests.Session();r=s.post(BASE+'/api/guest',json={'nickname':name},timeout=5)
    r.raise_for_status();return s,r.json()['player']

async def wait_type(ws,kind,timeout=4):
    async def _():
        while True:
            msg=json.loads(await ws.recv())
            if msg.get('type')==kind:return msg
    return await asyncio.wait_for(_(),timeout)

async def run():
    alice,ap=guest('Socket Alice')
    bob,bp=guest('Socket Bob')
    root=BASE.replace('http://','ws://').replace('https://','wss://')
    async with websockets.connect(root+'/ws',additional_headers={'Cookie':'agentopia_sid='+alice.cookies['agentopia_sid']}) as a:
      async with websockets.connect(root+'/ws',additional_headers={'Cookie':'agentopia_sid='+bob.cookies['agentopia_sid']}) as b:
        assert (await wait_type(a,'welcome'))['self']==ap['id']
        assert (await wait_type(b,'welcome'))['self']==bp['id']
        await b.send(json.dumps({'type':'chat','text':'Hi Alice from Bob'}))
        seen=await wait_type(a,'chat')
        assert seen['from']=='Socket Bob' and seen['text']=='Hi Alice from Bob',seen
        await a.send(json.dumps({'type':'input','dx':1,'dy':0}))
        await asyncio.sleep(.7)
        snap=await wait_type(b,'snapshot')
        pos=[p for p in snap['players'] if p['id']==ap['id']][0]['x']
        assert pos>18,pos
        await a.send(json.dumps({'type':'input','dx':0,'dy':0}))
        print('PASS: 2 live websocket clients, chat, shared positions and authoritative movement. Alice x:',round(pos,2))
    print('Online count:', requests.get(BASE+'/api/world',timeout=3).json()['online'])

if __name__=='__main__':asyncio.run(run())
