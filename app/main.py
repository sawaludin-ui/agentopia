"""Agentopia playable single-instance social world (FastAPI + SQLite + WebSockets).
Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
Security boundary: game state lives on server. External wallet keys never enter this app.
"""
from __future__ import annotations
import asyncio, contextlib, hashlib, json, math, os, re, secrets, sqlite3, time, threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from .crypto import (keccak256, login_typed_data, login_digest, recover_address,
                     address_word, calldata_join, contribution_digest, calldata_contribute,
                     sign_digest, contribution_typed_data)

ROOT=Path(__file__).resolve().parents[1]
NODES={
    'oak': {'x':13,'y':12,'kind':'wood','name':'Moonwood Tree','icon':'🌳'},
    'quarry': {'x':23,'y':12,'kind':'stone','name':'Starstone Quarry','icon':'🪨'},
    'power': {'x':18,'y':17,'kind':'energy','name':'Sunflower Reactor','icon':'⚡'},
}
WIDTH, HEIGHT=38,24
BUILDING_TARGET=160
BUILDING_ID=1
MAX_SPEED=3.2

class Input(BaseModel):
    pass
class GuestBody(BaseModel):
    nickname: str = 'Traveler'
class ProfileBody(BaseModel):
    nickname: str = Field(min_length=2,max_length=24)
    avatar: int = Field(ge=0,le=5)
class GatherBody(BaseModel):
    node_id: str
class BuildBody(BaseModel):
    material: str
    amount: int = Field(ge=1,le=20)
class ChallengeBody(BaseModel):
    address: str
class VerifyBody(BaseModel):
    address: str
    signature: str
class ContributeBody(BaseModel):
    material: str
    amount: int = Field(ge=1,le=20)
class TxBody(BaseModel):
    action_id: str
    tx_hash: str

@dataclass
class Config:
    db_path:str=os.getenv('AGENTOPIA_DB',str(ROOT/'agentopia.sqlite'))
    environment:str=os.getenv('AGENTOPIA_ENV','development')
    registry_mode:str=os.getenv('AGENTOPIA_REGISTRY_MODE','mock')
    rpc_url:str=os.getenv('AGENTOPIA_RPC_URL','')
    agent_id_contract:str=os.getenv('AGENTOPIA_AGENT_ID_CONTRACT','0x60b9262456de011f7d15a54cdd8c48baaa8b022f')
    game_contract:str=os.getenv('AGENTOPIA_GAME_CONTRACT','')
    oracle_private_key:str=os.getenv('AGENTOPIA_ORACLE_PRIVATE_KEY','')
    mock_holders:str=os.getenv('AGENTOPIA_MOCK_HOLDERS','')
    chain_id:int=int(os.getenv('AGENTOPIA_CHAIN_ID','56'))
    secure_cookie:bool=os.getenv('AGENTOPIA_SECURE_COOKIES','0')=='1'

class Repo:
    def __init__(self,path:str):
        self.db=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.lock=threading.RLock()
        self._create()

    def _create(self):
        with self.lock:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS players(
                id INTEGER PRIMARY KEY, nickname TEXT NOT NULL, avatar INTEGER NOT NULL DEFAULT 0,
                wood INTEGER NOT NULL DEFAULT 0 CHECK(wood>=0),
                stone INTEGER NOT NULL DEFAULT 0 CHECK(stone>=0),
                energy INTEGER NOT NULL DEFAULT 0 CHECK(energy>=0),
                xp INTEGER NOT NULL DEFAULT 0,
                x REAL NOT NULL DEFAULT 18, y REAL NOT NULL DEFAULT 12,
                wallet TEXT UNIQUE, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id),expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS claims(player_id INTEGER NOT NULL REFERENCES players(id),node TEXT NOT NULL, last_at REAL NOT NULL,PRIMARY KEY(player_id,node));
            CREATE TABLE IF NOT EXISTS construction(id INTEGER PRIMARY KEY, progress INTEGER NOT NULL DEFAULT 0, target INTEGER NOT NULL);
            INSERT OR IGNORE INTO construction(id,progress,target) VALUES(1,0,160);
            CREATE TABLE IF NOT EXISTS contribution_log(id INTEGER PRIMARY KEY,player_id INTEGER NOT NULL, material TEXT NOT NULL,amount INTEGER NOT NULL, created_at INTEGER NOT NULL,kind TEXT NOT NULL DEFAULT 'game', action_id TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS challenges(player_id INTEGER PRIMARY KEY, address TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS chain_actions(action_id TEXT PRIMARY KEY,player_id INTEGER NOT NULL,wallet TEXT NOT NULL,material TEXT NOT NULL,amount INTEGER NOT NULL,signature TEXT NOT NULL,deadline INTEGER NOT NULL,tx_hash TEXT UNIQUE,status TEXT NOT NULL DEFAULT 'prepared',created_at INTEGER NOT NULL);
            ''')

    def close(self):
        with self.lock: self.db.close()

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.execute('COMMIT')
            except Exception:
                self.db.execute('ROLLBACK')
                raise

    def player(self,player_id:int)->dict|None:
        with self.lock:
            row=self.db.execute('SELECT * FROM players WHERE id=?',(player_id,)).fetchone()
            return dict(row) if row else None

    def by_token(self,token:str|None)->dict|None:
        if not token: return None
        h=hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            row=self.db.execute('''SELECT p.* FROM sessions s JOIN players p ON p.id=s.player_id
               WHERE s.token_hash=? AND s.expires_at>?''',(h,int(time.time()))).fetchone()
            return dict(row) if row else None

    def new_guest(self,nickname:str)->tuple[str,dict]:
        token=secrets.token_urlsafe(36); now=int(time.time())
        with self.transaction() as db:
            cursor=db.execute('INSERT INTO players(nickname,created_at) VALUES(?,?)',(nickname,now))
            pid=cursor.lastrowid
            db.execute('INSERT INTO sessions(token_hash,player_id,expires_at) VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(),pid,now+7*86400))
        return token,self.player(pid)

    def update_profile(self,pid:int,nickname:str,avatar:int)->dict:
        with self.transaction() as db:
            db.execute('UPDATE players SET nickname=?,avatar=? WHERE id=?',(nickname,avatar,pid))
        return self.player(pid)

    def position(self,pid:int,x:float,y:float):
        with self.lock:
            self.db.execute('UPDATE players SET x=?, y=? WHERE id=?',(x,y,pid))

    def gather(self,pid:int,node_id:str,x:float,y:float)->dict:
        node=NODES.get(node_id)
        if not node: raise HTTPException(400,'Unknown resource node')
        if math.hypot(x-node['x'],y-node['y'])>1.9:
            raise HTTPException(400,'Move closer to the resource node')
        now=time.time(); item=node['kind']
        with self.transaction() as db:
            row=db.execute('SELECT last_at FROM claims WHERE player_id=? AND node=?',(pid,node_id)).fetchone()
            if row and now-row['last_at']<6.0:
                raise HTTPException(429,'Resource is recovering; try again soon')
            current=db.execute(f'SELECT {item} FROM players WHERE id=?',(pid,)).fetchone()[0]
            if current>=99: raise HTTPException(409,'Inventory is full')
            db.execute('''INSERT INTO claims(player_id,node,last_at) VALUES(?,?,?)
                ON CONFLICT(player_id,node) DO UPDATE SET last_at=excluded.last_at''',(pid,node_id,now))
            db.execute(f'UPDATE players SET {item}={item}+1,xp=xp+2 WHERE id=?',(pid,))
        return {'material':item,'amount':1,'player':self.player(pid)}

    def build(self,pid:int,material:str,amount:int)->dict:
        if material not in ('wood','stone','energy'): raise HTTPException(400,'Invalid material')
        with self.transaction() as db:
            inventory=db.execute(f'SELECT {material} FROM players WHERE id=?',(pid,)).fetchone()[0]
            progress,target=db.execute('SELECT progress,target FROM construction WHERE id=1').fetchone()
            if inventory<amount: raise HTTPException(409,'Not enough material')
            if progress>=target: raise HTTPException(409,'The bridge is already complete')
            if progress+amount>target: raise HTTPException(409,f'Only {target-progress} progress remains')
            db.execute(f'UPDATE players SET {material}={material}-?,xp=xp+? WHERE id=?',(amount,amount*3,pid))
            db.execute('UPDATE construction SET progress=progress+? WHERE id=1',(amount,))
            db.execute('INSERT INTO contribution_log(player_id,material,amount,created_at) VALUES(?,?,?,?)',(pid,material,amount,int(time.time())))
        return {'player':self.player(pid),'world':self.world()}

    def world(self)->dict:
        with self.lock:
            row=self.db.execute('SELECT progress,target FROM construction WHERE id=1').fetchone()
            return {'bridge':{'progress':row[0],'target':row[1],'complete':row[0]>=row[1]},'nodes':NODES,'width':WIDTH,'height':HEIGHT}

    def leaderboard(self)->list[dict]:
        with self.lock:
            rows=self.db.execute('''SELECT p.id,p.nickname,p.avatar,CASE WHEN p.wallet IS NULL THEN 0 ELSE 1 END AS verified,p.xp,COALESCE(SUM(c.amount),0) AS contributed
              FROM players p LEFT JOIN contribution_log c ON c.player_id=p.id
              GROUP BY p.id ORDER BY contributed DESC,p.xp DESC LIMIT 25''').fetchall()
            return [dict(r) for r in rows]

    def challenge(self,pid:int,addr:str,chain_id:int)->dict:
        if not re.fullmatch('0x[0-9a-fA-F]{40}',addr): raise HTTPException(400,'Invalid wallet address')
        nonce=secrets.token_hex(16); deadline=int(time.time())+300
        with self.transaction() as db:
            db.execute('INSERT INTO challenges(player_id,address,nonce,expires_at) VALUES(?,?,?,?) ON CONFLICT(player_id) DO UPDATE SET address=excluded.address,nonce=excluded.nonce,expires_at=excluded.expires_at',(pid,addr.lower(),nonce,deadline))
        return login_typed_data(addr,nonce,deadline,chain_id)

    def get_challenge(self,pid:int):
        with self.lock:
            row=self.db.execute('SELECT * FROM challenges WHERE player_id=?',(pid,)).fetchone()
            return dict(row) if row else None

    def bind_wallet(self,pid:int,addr:str,nonce:str)->tuple[dict,str|None]:
        """Link a new holder or reauthenticate the previously linked player.
        A valid fresh EIP-712 signature is required in either case.
        """
        new_token=None
        with self.transaction() as db:
            row=db.execute('SELECT nonce,expires_at,address FROM challenges WHERE player_id=?',(pid,)).fetchone()
            if not row or row['nonce']!=nonce or row['expires_at']<time.time() or row['address'].lower()!=addr.lower():
                raise HTTPException(409,'Challenge expired or already used')
            existing=db.execute('SELECT id FROM players WHERE wallet=?',(addr.lower(),)).fetchone()
            effective_id=existing['id'] if existing else pid
            if not existing:
                db.execute('UPDATE players SET wallet=? WHERE id=?',(addr.lower(),pid))
            else:
                # Re-authentication from a different device never steals the account;
                # the cryptographically proven holder receives a new session.
                new_token=secrets.token_urlsafe(36)
                db.execute('INSERT INTO sessions(token_hash,player_id,expires_at) VALUES(?,?,?)',
                           (hashlib.sha256(new_token.encode()).hexdigest(),effective_id,int(time.time())+7*86400))
            db.execute('DELETE FROM challenges WHERE player_id=?',(pid,))
        return self.player(effective_id),new_token

    def prepare_chain(self,pid:int,material:str,amount:int,key:int,contract:str,chain_id:int,production_crypto:bool=False)->dict:
        if material not in ('wood','stone','energy'):raise HTTPException(400,'Invalid material')
        action=secrets.token_bytes(32); aid='0x'+action.hex(); deadline=int(time.time())+1200
        with self.transaction() as db:
            player=db.execute('SELECT * FROM players WHERE id=?',(pid,)).fetchone()
            if not player['wallet']: raise HTTPException(403,'Agent ID verification required')
            if player[material]<amount: raise HTTPException(409,'Not enough material')
            # Reserving material here prevents double-spend while confirmation is pending.
            db.execute(f'UPDATE players SET {material}={material}-? WHERE id=?',(amount,pid))
            digest=contribution_digest(player['wallet'],BUILDING_ID,amount,action,deadline,contract,chain_id)
            if production_crypto:
                from eth_account import Account
                from eth_account.messages import encode_typed_data
                typed=contribution_typed_data(player['wallet'],BUILDING_ID,amount,action,deadline,contract,chain_id)
                signature=Account.sign_message(encode_typed_data(full_message=typed),private_key=key.to_bytes(32,'big')).signature
                sig='0x'+bytes(signature).hex()
            else:
                sig=sign_digest(key,digest)
            db.execute('''INSERT INTO chain_actions(action_id,player_id,wallet,material,amount,signature,deadline,created_at)
                VALUES(?,?,?,?,?,?,?,?)''',(aid,pid,player['wallet'],material,amount,sig,deadline,int(time.time())))
        return {'actionId':aid,'deadline':deadline,'material':material,'amount':amount,'signature':sig,
                'to':contract,'chainId':chain_id,'data':calldata_contribute(BUILDING_ID,amount,action,deadline,sig)}

    def get_action(self,action:str,pid:int)->dict|None:
        with self.lock:
            row=self.db.execute('SELECT * FROM chain_actions WHERE action_id=? AND player_id=?',(action,pid)).fetchone()
            return dict(row) if row else None

    def record_hash(self,pid:int,aid:str,txhash:str):
        if not re.fullmatch('0x[0-9a-fA-F]{64}',txhash):raise HTTPException(400,'Invalid transaction hash')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM chain_actions WHERE action_id=? AND player_id=?',(aid,pid)).fetchone()
            if not row:raise HTTPException(404,'Action not found')
            if row['tx_hash'] and row['tx_hash'].lower()!=txhash.lower():raise HTTPException(409,'Transaction already bound')
            if row['status']=='confirmed':return
            if row['status']=='expired':raise HTTPException(409,'Voucher expired and inventory was restored')
            db.execute('UPDATE chain_actions SET tx_hash=?,status=? WHERE action_id=?',(txhash.lower(),'submitted',aid))

    def cancel_chain(self,pid:int,aid:str):
        with self.transaction() as db:
            row=db.execute('SELECT * FROM chain_actions WHERE action_id=? AND player_id=?',(aid,pid)).fetchone()
            if not row:raise HTTPException(404,'Action not found')
            if row['status']=='expired':return
            if row['status'] not in ('prepared','submitted') or row['deadline']+60>time.time():
                raise HTTPException(409,'Voucher is still valid or action already finalized')
            db.execute(f'UPDATE players SET {row["material"]}={row["material"]}+? WHERE id=?', (row['amount'],pid))
            db.execute('UPDATE chain_actions SET status=? WHERE action_id=?',('expired',aid))

    def confirm_chain(self,pid:int,aid:str)->dict:
        with self.transaction() as db:
            row=db.execute('SELECT * FROM chain_actions WHERE action_id=? AND player_id=?',(aid,pid)).fetchone()
            if not row: raise HTTPException(404,'Action not found')
            if row['status']=='confirmed':return dict(row)
            if row['status']!='submitted':raise HTTPException(409,'Transaction not submitted')
            exists=db.execute('SELECT id FROM contribution_log WHERE action_id=?',(aid,)).fetchone()
            if not exists:
                db.execute('INSERT INTO contribution_log(player_id,material,amount,created_at,kind,action_id) VALUES(?,?,?,?,?,?)',
                           (pid,row['material'],row['amount'],int(time.time()),'chain',aid))
                db.execute('UPDATE players SET xp=xp+? WHERE id=?',(row['amount']*5,pid))
                # The contract tracks season-wide proof points; the local bridge
                # additionally advances without ever exceeding its own target.
                db.execute('UPDATE construction SET progress=MIN(target,progress+?) WHERE id=1',(row['amount'],))
            db.execute('UPDATE chain_actions SET status=? WHERE action_id=?',('confirmed',aid))
        return self.get_action(aid,pid)

class World:
    def __init__(self,repo:Repo):
        self.repo=repo
        self.clients:dict[int,WebSocket]={}
        self.actors:dict[int,dict]={}
        self.inputs:dict[int,tuple[float,float]]={}
        self.chat_last:dict[int,float]={}
        self.task=None
        self.last_saved=0.0

    @staticmethod
    def walkable(x:float,y:float,bridge_complete:bool)->bool:
        if x<1 or y<1 or x>WIDTH-2 or y>HEIGHT-2:return False
        # river, with bridge only after completed
        if 29<=x<=31 and not(bridge_complete and 10<=y<=13):return False
        # houses and kiosks
        for rect in [(4,3,10,8),(14,3,20,7),(24,3,28,8),(5,17,11,21),(22,17,27,21)]:
            if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]:return False
        return True

    async def attach(self,pid:int,ws:WebSocket):
        if pid in self.clients:
            with contextlib.suppress(Exception):await self.clients[pid].close(code=4000,reason='Signed in elsewhere')
        self.clients[pid]=ws
        p=self.repo.player(pid)
        self.actors[pid]={'id':pid,'x':float(p['x']),'y':float(p['y']),'nickname':p['nickname'],'avatar':p['avatar'],'verified':bool(p['wallet'])}
        self.inputs[pid]=(0.0,0.0)
        await ws.send_json({'type':'welcome','self':pid,'world':self.repo.world()})
        await self.broadcast({'type':'notice','text':f'{p["nickname"]} arrived in town.'})

    async def detach(self,pid:int,ws:WebSocket):
        if self.clients.get(pid) is not ws:return
        actor=self.actors.get(pid)
        if actor:self.repo.position(pid,actor['x'],actor['y'])
        self.clients.pop(pid,None);self.actors.pop(pid,None);self.inputs.pop(pid,None)

    async def broadcast(self,payload:dict):
        dead=[]
        for pid,ws in list(self.clients.items()):
            try:await ws.send_json(payload)
            except Exception:dead.append((pid,ws))
        for pid,ws in dead:await self.detach(pid,ws)

    async def tick(self):
        previous=time.monotonic(); last_cast=0
        while True:
            await asyncio.sleep(.05)
            now=time.monotonic(); dt=min(now-previous,.1);previous=now
            bridge=self.repo.world()['bridge']['complete']
            for pid,actor in list(self.actors.items()):
                dx,dy=self.inputs.get(pid,(0,0))
                mag=math.hypot(dx,dy)
                if mag>0:
                    dx/=mag;dy/=mag
                    nx=actor['x']+dx*MAX_SPEED*dt;ny=actor['y']+dy*MAX_SPEED*dt
                    if self.walkable(nx,actor['y'],bridge):actor['x']=nx
                    if self.walkable(actor['x'],ny,bridge):actor['y']=ny
            if now-last_cast>=.10:
                last_cast=now
                await self.broadcast({'type':'snapshot','players':list(self.actors.values()),'online':len(self.actors)})
            if now-self.last_saved>5:
                self.last_saved=now
                for pid,a in list(self.actors.items()): self.repo.position(pid,a['x'],a['y'])

async def rpc_call(url:str,method:str,params:list)->Any:
    timeout=aiohttp.ClientTimeout(total=7)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(url,json={'jsonrpc':'2.0','id':1,'method':method,'params':params}) as resp:
                if resp.status!=200:raise HTTPException(503,'RPC request failed')
                raw=await resp.json()
                if 'error' in raw:raise HTTPException(503,'RPC error: '+str(raw['error'].get('message','unknown'))[:120])
                return raw.get('result')
    except (aiohttp.ClientError,asyncio.TimeoutError) as exc:
        raise HTTPException(503,'RPC unavailable') from exc

async def holder_verified(cfg:Config,addr:str)->bool:
    if cfg.registry_mode=='mock':
        if cfg.environment!='development':raise HTTPException(503,'Mock Agent ID is not permitted outside development')
        return addr.lower() in {x.strip().lower() for x in cfg.mock_holders.split(',') if x.strip()}
    if cfg.registry_mode not in ('mainnet','testnet') or not cfg.rpc_url:
        raise HTTPException(503,'Agent ID registry not configured')
    if cfg.registry_mode=='mainnet' and cfg.chain_id!=56:raise HTTPException(503,'Mainnet chain mismatch')
    result=await rpc_call(cfg.rpc_url,'eth_call',[{'to':cfg.agent_id_contract,'data':'0x70a08231'+address_word(addr).hex()},'latest'])
    return int(result or '0x0',16)>0

def create_app(config:Config|None=None):
    cfg=config or Config()
    if cfg.registry_mode not in ('mock','mainnet','testnet'):
        raise RuntimeError('Unknown Agent ID mode')
    if cfg.registry_mode=='mainnet' and cfg.chain_id!=56:
        raise RuntimeError('BNB mainnet requires chain ID 56')
    if cfg.registry_mode=='testnet' and cfg.chain_id!=97:
        raise RuntimeError('BNB testnet requires chain ID 97')
    official='0x60b9262456de011f7d15a54cdd8c48baaa8b022f'
    if cfg.registry_mode=='mainnet' and cfg.agent_id_contract.lower()!=official:
        raise RuntimeError('Mainnet requires the official Binance Agent ID registry')
    if cfg.registry_mode=='testnet' and cfg.agent_id_contract.lower()==official:
        raise RuntimeError('Testnet requires its own deployed mock registry address')
    if cfg.environment!='development' and cfg.registry_mode=='mock':
        raise RuntimeError('Mock registry cannot run outside development')
    if cfg.environment!='development' and not cfg.secure_cookie:
        raise RuntimeError('Production requires AGENTOPIA_SECURE_COOKIES=1')
    if cfg.environment!='development':
        try:
            import eth_account  # noqa: F401 — reviewed library for real signatures
        except ImportError as exc:
            raise RuntimeError('Production requires pip package eth-account for EIP-712 signature verification') from exc
    repo=Repo(cfg.db_path)
    world=World(repo)

    @asynccontextmanager
    async def lifespan(app:FastAPI):
        world.task=asyncio.create_task(world.tick())
        yield
        world.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await world.task
        for pid,a in list(world.actors.items()):repo.position(pid,a['x'],a['y'])
        repo.close()

    app=FastAPI(title='Agentopia API',version='0.1',lifespan=lifespan,docs_url='/api/docs' if cfg.environment=='development' else None)
    app.state.repo=repo;app.state.world=world;app.state.config=cfg

    @app.middleware('http')
    async def security_headers(request:Request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']=("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:; img-src 'self' data:; font-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    signup_times:dict[str,list[float]]={}

    def current(req:Request)->dict:
        p=repo.by_token(req.cookies.get('agentopia_sid'))
        if not p:raise HTTPException(401,'Create a player first')
        return p

    @app.get('/')
    def home():return FileResponse(ROOT/'web/index.html')
    @app.get('/style.css')
    def css():return FileResponse(ROOT/'web/style.css',media_type='text/css')
    @app.get('/game.js')
    def js():return FileResponse(ROOT/'web/game.js',media_type='application/javascript')
    @app.get('/health')
    def health():return {'ok':True,'version':'0.1','chainMode':cfg.registry_mode}

    @app.post('/api/guest')
    def guest(payload:GuestBody,response:Response,request:Request):
        addr=request.client.host if request.client else 'unknown'
        now=time.monotonic()
        recent=[t for t in signup_times.get(addr,[]) if now-t<60]
        if len(recent)>=50:raise HTTPException(429,'Too many guest accounts from this address')
        recent.append(now);signup_times[addr]=recent
        nickname=payload.nickname.strip()
        if not 2<=len(nickname)<=22 or not re.fullmatch(r'[\w .-]{2,22}',nickname,re.UNICODE):
            raise HTTPException(400,'Nickname: 2–22 letters, numbers, spaces, underscores, periods, or hyphens')
        token,p=repo.new_guest(nickname)
        response.set_cookie('agentopia_sid',token,max_age=7*86400,httponly=True,secure=cfg.secure_cookie,samesite='lax',path='/')
        return {'player':p,'world':repo.world()}

    @app.get('/api/me')
    def me(req:Request):return {'player':current(req),'world':repo.world(),'online':len(world.actors),'chainReady':bool(cfg.game_contract),'mode':cfg.registry_mode}

    @app.post('/api/profile')
    async def profile(req:Request,payload:ProfileBody):
        p=current(req);name=payload.nickname.strip()
        if not re.fullmatch(r'[\w .-]{2,22}',name,re.UNICODE):raise HTTPException(400,'Invalid nickname')
        updated=repo.update_profile(p['id'],name,payload.avatar)
        if p['id'] in world.actors:
            world.actors[p['id']]['nickname']=name;world.actors[p['id']]['avatar']=payload.avatar
        return {'player':updated}

    @app.get('/api/leaderboard')
    def leaderboard():return {'players':repo.leaderboard()}

    @app.post('/api/gather')
    async def gather(req:Request,payload:GatherBody):
        p=current(req)
        a=world.actors.get(p['id'])
        x,y=(a['x'],a['y']) if a else (p['x'],p['y'])
        return repo.gather(p['id'],payload.node_id,x,y)

    @app.post('/api/build')
    async def build(req:Request,payload:BuildBody):
        p=current(req);a=world.actors.get(p['id'])
        x,y=(a['x'],a['y']) if a else (p['x'],p['y'])
        if math.hypot(x-27,y-12)>3.0:raise HTTPException(400,'Move to the bridge construction site')
        result=repo.build(p['id'],payload.material,payload.amount)
        await world.broadcast({'type':'construction','bridge':result['world']['bridge']})
        return result

    @app.get('/api/world')
    def world_state():return {'world':repo.world(),'online':len(world.actors)}

    @app.get('/api/pix')
    def companion(req:Request):
        p=current(req)
        prog=repo.world()['bridge']
        advice='The bridge is complete! Explore across the river.' if prog['complete'] else (
            f'Bridge is {prog["progress"]}/{prog["target"]}. Find trees, quarry stones, or collect energy, then donate at the bridge site!')
        return {'name':'PIX','text':f'Hey {p["nickname"]}! {advice} I can guide you, but I never control your wallet.'}

    @app.post('/api/identity/challenge')
    def challenge(req:Request,payload:ChallengeBody):
        p=current(req)
        typed=repo.challenge(p['id'],payload.address,cfg.chain_id)
        return {'typedData':typed,'expiresIn':300,'notice':'Sign using your own wallet. Never share keys or pairing codes.'}

    @app.post('/api/identity/verify')
    async def verify(req:Request,response:Response,payload:VerifyBody):
        p=current(req);row=repo.get_challenge(p['id'])
        if not row or row['expires_at']<=time.time() or row['address']!=payload.address.lower():
            raise HTTPException(409,'Challenge expired or address mismatch')
        try:
            digest=login_digest(payload.address,row['nonce'],row['expires_at'],cfg.chain_id)
            if cfg.environment=='development':
                recovered=recover_address(digest,payload.signature)
            else:
                from eth_account import Account
                from eth_account.messages import encode_typed_data
                data=login_typed_data(payload.address,row['nonce'],row['expires_at'],cfg.chain_id)
                recovered=Account.recover_message(encode_typed_data(full_message=data),signature=payload.signature)
        except (ValueError,OverflowError,TypeError) as ex:
            raise HTTPException(401,'Invalid signature') from ex
        if recovered.lower()!=payload.address.lower():raise HTTPException(401,'Signature does not match address')
        if not await holder_verified(cfg,recovered):raise HTTPException(403,'Address does not hold Agent ID')
        updated,recovery_token=repo.bind_wallet(p['id'],recovered,row['nonce'])
        if recovery_token:
            response.set_cookie('agentopia_sid',recovery_token,max_age=7*86400,httponly=True,secure=cfg.secure_cookie,samesite='lax',path='/')
        if p['id'] in world.actors and updated['id']==p['id']:
            world.actors[p['id']]['verified']=True
        return {'verified':True,'player':updated,'recoveredAccount':bool(recovery_token)}

    @app.get('/api/chain/join')
    def prepare_join(req:Request):
        p=current(req)
        if not p['wallet']:raise HTTPException(403,'Verify Agent ID first')
        if not cfg.game_contract:raise HTTPException(503,'Game contract not configured')
        return {'to':cfg.game_contract,'from':p['wallet'],'data':calldata_join(),'value':'0x0','chainId':cfg.chain_id,
                'warning':'Wallet holder must review and approve this transaction.'}

    @app.post('/api/chain/contribution')
    async def contribution(req:Request,payload:ContributeBody):
        p=current(req)
        a=world.actors.get(p['id'])
        x,y=(a['x'],a['y']) if a else (p['x'],p['y'])
        if math.hypot(x-27,y-12)>3.0:raise HTTPException(400,'Move to the bridge construction site')
        if not cfg.game_contract or not cfg.oracle_private_key:raise HTTPException(503,'Chain contribution unavailable: contract and oracle required')
        # Verify actual contract citizenship before reserving materials.
        if cfg.environment!='development':
            if not cfg.rpc_url:raise HTTPException(503,'RPC required for on-chain citizenship check')
            selector=keccak256(b'citizens(address)')[:4]
            raw=await rpc_call(cfg.rpc_url,'eth_call',[{'to':cfg.game_contract,'data':'0x'+(selector+address_word(p['wallet'])).hex()},'latest'])
            if int(raw or '0x0',16)==0:
                raise HTTPException(409,'Join City on-chain first, and wait for confirmation')
        try:key=int(cfg.oracle_private_key.removeprefix('0x'),16)
        except ValueError as exc:raise HTTPException(503,'Oracle configuration invalid') from exc
        result=repo.prepare_chain(p['id'],payload.material,payload.amount,key,cfg.game_contract,cfg.chain_id,production_crypto=cfg.environment!='development')
        result['from']=p['wallet'];result['value']='0x0'
        result['warning']='Prepared voucher reserves materials; requires independent wallet approval.'
        return result

    @app.post('/api/chain/submit')
    def submit(req:Request,payload:TxBody):
        p=current(req);repo.record_hash(p['id'],payload.action_id,payload.tx_hash)
        return {'status':'submitted'}

    @app.get('/api/chain/action/{action_id}')
    async def chain_action(req:Request,action_id:str):
        p=current(req);row=repo.get_action(action_id,p['id'])
        if not row:raise HTTPException(404,'Action not found')
        if row['status']=='confirmed':return {'status':'confirmed','actionId':action_id}
        if row['status']=='expired':return {'status':'expired','actionId':action_id}
        if not row['tx_hash']:return {'status':'prepared','actionId':action_id}
        if not cfg.rpc_url or not cfg.game_contract:raise HTTPException(503,'Chain RPC not configured')
        receipt=await rpc_call(cfg.rpc_url,'eth_getTransactionReceipt',[row['tx_hash']])
        if receipt is None:return {'status':'pending','actionId':action_id}
        if receipt.get('status')!='0x1':return {'status':'failed','actionId':action_id,'note':'Material remains reserved; contact the operator to reconcile.'}
        if receipt.get('to','').lower()!=cfg.game_contract.lower():raise HTTPException(409,'Receipt target mismatch')
        latest=await rpc_call(cfg.rpc_url,'eth_blockNumber',[])
        if int(latest,16)-int(receipt['blockNumber'],16)<2:return {'status':'confirming','actionId':action_id}
        topic='0x'+keccak256(b'Contributed(address,uint256,uint256,bytes32)').hex()
        found=False
        for log in receipt.get('logs',[]):
            topics=log.get('topics',[])
            if (log.get('address','').lower()==cfg.game_contract.lower() and len(topics)>=3 and topics[0].lower()==topic.lower() and
                int(topics[1],16)==int(row['wallet'],16) and int(topics[2],16)==BUILDING_ID and
                int(log.get('data','0x')[:66],16)==row['amount'] and
                log.get('data','0x')[66:130].lower()==row['action_id'][2:].lower()):
                found=True;break
        if not found:raise HTTPException(409,'Matching contract event not found')
        repo.confirm_chain(p['id'],action_id)
        await world.broadcast({'type':'construction','bridge':repo.world()['bridge']})
        await world.broadcast({'type':'onchain','text':'An on-chain contribution was confirmed!'})
        return {'status':'confirmed','actionId':action_id}

    @app.post('/api/chain/cancel/{action_id}')
    async def cancel_chain(req:Request,action_id:str):
        p=current(req)
        row=repo.get_action(action_id,p['id'])
        if not row:raise HTTPException(404,'Action not found')
        if row['status']=='expired':return {'status':'expired'}
        if not re.fullmatch('0x[0-9a-fA-F]{64}',action_id):raise HTTPException(400,'Invalid action ID')
        if row['deadline']+60>time.time():raise HTTPException(409,'Voucher must first expire')
        if not cfg.rpc_url or not cfg.game_contract:
            raise HTTPException(503,'Cannot safely release reserved items without a live RPC check')
        # Query contract replay state; after voucher expiry no new successful
        # transaction can use this action ID. This check avoids double credits.
        selector=keccak256(b'usedActions(bytes32)')[:4]
        calldata='0x'+(selector+bytes.fromhex(action_id.removeprefix('0x'))).hex()
        used=await rpc_call(cfg.rpc_url,'eth_call',[{'to':cfg.game_contract,'data':calldata},'latest'])
        if int(used or '0x0',16)!=0:
            raise HTTPException(409,'On-chain action was used; provide transaction hash to reconcile')
        repo.cancel_chain(p['id'],action_id)
        return {'status':'expired','player':repo.player(p['id'])}

    @app.websocket('/ws')
    async def ws_handler(ws:WebSocket):
        # Same-origin protection: tolerate missing Origin from non-browser test clients.
        origin=ws.headers.get('origin')
        if origin:
            host=ws.headers.get('host','')
            if origin.rstrip('/').split('://')[-1].lower()!=host.lower():
                await ws.close(code=4403);return
        player=repo.by_token(ws.cookies.get('agentopia_sid'))
        if not player:
            await ws.close(code=4401);return
        if len(world.clients)>=60 and player['id'] not in world.clients:
            await ws.close(code=4408,reason='Town is at capacity');return
        await ws.accept();pid=player['id'];await world.attach(pid,ws)
        try:
            while True:
                msg=await ws.receive_json()
                if world.clients.get(pid) is not ws:break
                kind=msg.get('type') if isinstance(msg,dict) else None
                if kind=='input':
                    dx=float(msg.get('dx',0));dy=float(msg.get('dy',0))
                    if not math.isfinite(dx) or not math.isfinite(dy):continue
                    world.inputs[pid]=(max(-1,min(1,dx)),max(-1,min(1,dy)))
                elif kind=='chat':
                    now=time.monotonic()
                    if now-world.chat_last.get(pid,0)<1.5:continue
                    text=msg.get('text','')
                    if not isinstance(text,str):continue
                    text=''.join(ch for ch in text.strip() if ch.isprintable())[:160]
                    if not text:continue
                    world.chat_last[pid]=now
                    await world.broadcast({'type':'chat','from':world.actors[pid]['nickname'],'playerId':pid,'text':text})
                elif kind=='emote':
                    value=msg.get('value')
                    if value in ('wave','heart','dance','wow'):
                        await world.broadcast({'type':'emote','playerId':pid,'value':value})
        except (WebSocketDisconnect,RuntimeError,ValueError,TypeError):pass
        finally:await world.detach(pid,ws)

    return app

app=create_app()
