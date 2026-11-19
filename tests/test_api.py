import tempfile,time,pytest
from fastapi.testclient import TestClient
from app.main import create_app,Config,NODES
from app.crypto import address_from_private_key, login_digest, sign_digest

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as d:
        cfg=Config(db_path=f'{d}/test.db',environment='development',registry_mode='mock',
                   chain_id=56,mock_holders=address_from_private_key(1),game_contract='',
                   oracle_private_key='',rpc_url='',secure_cookie=False)
        app=create_app(cfg)
        with TestClient(app) as c:
            yield c

@pytest.fixture
def player(client):
    response=client.post('/api/guest',json={'nickname':'Moon Walker'})
    assert response.status_code==200
    return response.json()['player']

def test_guest_me_and_profile(client,player):
    assert client.get('/health').json()['ok']
    p=client.get('/api/me').json()['player']
    assert p['nickname']=='Moon Walker'
    response=client.post('/api/profile',json={'nickname':'New Hero','avatar':3})
    assert response.status_code==200
    assert response.json()['player']['avatar']==3
    assert client.get('/api/me').json()['player']['nickname']=='New Hero'

def test_guest_reject_bad_name(client):
    assert client.post('/api/guest',json={'nickname':'x'}).status_code==400
    assert client.post('/api/guest',json={'nickname':'<script>alert(1)</script>'}).status_code==400

def test_unauthorized_and_wallet_ownership(client):
    assert client.get('/api/me').status_code==401
    address=address_from_private_key(1)
    assert client.post('/api/identity/challenge',json={'address':address}).status_code==401

def test_gather_proximity_cooldown_build_and_inventory(client,player):
    db=client.app.state.repo
    # set true server position at the resource location, as if walked there.
    db.position(player['id'],NODES['oak']['x'],NODES['oak']['y'])
    result=client.post('/api/gather',json={'node_id':'oak'})
    assert result.status_code==200,result.text
    assert result.json()['player']['wood']==1
    assert client.post('/api/gather',json={'node_id':'oak'}).status_code==429
    # Build must be near the bridge and within inventory limits.
    assert client.post('/api/build',json={'material':'wood','amount':1}).status_code==400
    db.position(player['id'],27,12)
    assert client.post('/api/build',json={'material':'stone','amount':1}).status_code==409
    built=client.post('/api/build',json={'material':'wood','amount':1})
    assert built.status_code==200,built.text
    assert built.json()['world']['bridge']['progress']==1
    assert built.json()['player']['wood']==0
    board=client.get('/api/leaderboard').json()['players']
    assert board[0]['contributed']==1

def test_gather_tamper_fail(client,player):
    assert client.post('/api/gather',json={'node_id':'nonexistent'}).status_code==400
    assert client.post('/api/gather',json={'node_id':'oak'}).status_code==400
    assert client.post('/api/build',json={'material':'fiat','amount':1}).status_code==400
    assert client.post('/api/build',json={'material':'wood','amount':100000}).status_code==422

def test_websocket_join_snapshot_and_chat(client,player):
    with client.websocket_connect('/ws') as ws:
        assert ws.receive_json()['type']=='welcome'
        # notice emitted by attach before first snapshot
        assert ws.receive_json()['type']=='notice'
        ws.send_json({'type':'chat','text':'Hello valley! 🌻'})
        data=ws.receive_json()
        # Could be snapshot before chat due to 10Hz tick.
        while data['type']!='chat':data=ws.receive_json()
        assert data['text']=='Hello valley! 🌻'
        ws.send_json({'type':'input','dx':1,'dy':0})
        found=False
        for _ in range(12):
            event=ws.receive_json()
            if event['type']=='snapshot' and any(a['id']==player['id'] and a['x']>18 for a in event['players']):
                found=True;break
        assert found

def test_verify_agent_id_signature_and_replay(client,player):
    addr=address_from_private_key(1)
    response=client.post('/api/identity/challenge',json={'address':addr})
    assert response.status_code==200
    d=response.json()['typedData'];msg=d['message']
    assert client.post('/api/identity/verify',json={'address':addr,'signature':'0x'+'00'*65}).status_code==401
    sig=sign_digest(1,login_digest(addr,msg['nonce'],msg['expiresAt']))
    r=client.post('/api/identity/verify',json={'address':addr,'signature':sig})
    assert r.status_code==200,r.text
    assert r.json()['player']['wallet']==addr
    assert client.post('/api/identity/verify',json={'address':addr,'signature':sig}).status_code==409
    assert client.get('/api/chain/join').status_code==503

def test_nonholder_denied_even_valid_signature(client,player):
    addr=address_from_private_key(2)
    data=client.post('/api/identity/challenge',json={'address':addr}).json()['typedData']['message']
    sig=sign_digest(2,login_digest(addr,data['nonce'],data['expiresAt']))
    assert client.post('/api/identity/verify',json={'address':addr,'signature':sig}).status_code==403

def test_session_cross_player_isolation(client,player):
    first=player['id'];root=client.app.state.repo
    r=client.post('/api/guest',json={'nickname':'Second Player'});second=r.json()['player']['id']
    assert first!=second
    assert client.get('/api/me').json()['player']['id']==second
    assert root.player(first)['nickname']=='Moon Walker'

def test_live_and_mock_separation():
    with tempfile.TemporaryDirectory() as d:
        cfg=Config(db_path=f'{d}/prod.sqlite',environment='production',registry_mode='mock',secure_cookie=True)
        with pytest.raises(RuntimeError):create_app(cfg)

def test_wallet_account_recovery_with_fresh_signature(client,player):
    addr=address_from_private_key(1)
    def authenticate():
        msg=client.post('/api/identity/challenge',json={'address':addr}).json()['typedData']['message']
        sig=sign_digest(1,login_digest(addr,msg['nonce'],msg['expiresAt']))
        return client.post('/api/identity/verify',json={'address':addr,'signature':sig})
    first=authenticate()
    assert first.status_code==200
    assert not first.json()['recoveredAccount']
    initial_id=first.json()['player']['id']
    assert client.post('/api/guest',json={'nickname':'Second Device'}).status_code==200
    second=authenticate()
    assert second.status_code==200,second.text
    assert second.json()['recoveredAccount']
    assert second.json()['player']['id']==initial_id
    assert client.get('/api/me').json()['player']['id']==initial_id

def test_signed_voucher_reserves_inventory_and_onchain_digest(client,player):
    from app.crypto import contribution_digest,recover_address,calldata_contribute
    db=client.app.state.repo
    addr=address_from_private_key(1)
    message=client.post('/api/identity/challenge',json={'address':addr}).json()['typedData']['message']
    sig=sign_digest(1,login_digest(addr,message['nonce'],message['expiresAt']))
    assert client.post('/api/identity/verify',json={'address':addr,'signature':sig}).status_code==200
    db.position(player['id'],27,12)
    # Give one material by a server-controlled harvest action; choose in-game location.
    db.position(player['id'],13,12)
    assert client.post('/api/gather',json={'node_id':'oak'}).status_code==200
    db.position(player['id'],27,12)
    contract=address_from_private_key(5)
    config=client.app.state.config
    config.game_contract=contract
    config.oracle_private_key='0x'+'0'*63+'3'
    result=client.post('/api/chain/contribution',json={'material':'wood','amount':1})
    assert result.status_code==200,result.text
    proof=result.json()
    digest=contribution_digest(addr,1,1,bytes.fromhex(proof['actionId'][2:]),proof['deadline'],contract,56)
    assert recover_address(digest,proof['signature'])==address_from_private_key(3)
    assert proof['data']==calldata_contribute(1,1,bytes.fromhex(proof['actionId'][2:]),proof['deadline'],proof['signature'])
    assert client.get('/api/me').json()['player']['wood']==0
    assert client.post('/api/chain/contribution',json={'material':'wood','amount':1}).status_code==409
    assert client.post('/api/chain/submit',json={'action_id':proof['actionId'],'tx_hash':'0xbad'}).status_code==400
    assert client.get('/api/chain/action/'+proof['actionId']).json()['status']=='prepared'

def test_replay_gather_parallel_has_single_winner(client,player):
    from concurrent.futures import ThreadPoolExecutor
    db=client.app.state.repo
    db.position(player['id'],13,12)
    def request(_):
        return client.post('/api/gather',json={'node_id':'oak'}).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses=list(pool.map(request,range(8)))
    assert statuses.count(200)==1
    assert statuses.count(429)==7
    assert client.get('/api/me').json()['player']['wood']==1


def test_websocket_bad_origin_is_rejected(client,player):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws',headers={'origin':'https://attacker.invalid'}):
            pass


def test_expired_onchain_voucher_safe_recovery(client,player,monkeypatch):
    import importlib
    mod=importlib.import_module('app.main')
    db=client.app.state.repo
    addr=address_from_private_key(1)
    msg=client.post('/api/identity/challenge',json={'address':addr}).json()['typedData']['message']
    sig=sign_digest(1,login_digest(addr,msg['nonce'],msg['expiresAt']))
    assert client.post('/api/identity/verify',json={'address':addr,'signature':sig}).status_code==200
    db.position(player['id'],13,12)
    assert client.post('/api/gather',json={'node_id':'oak'}).status_code==200
    db.position(player['id'],27,12)
    cfg=client.app.state.config
    cfg.game_contract=address_from_private_key(5)
    cfg.oracle_private_key='0x'+'0'*63+'3'
    cfg.rpc_url='http://stub.invalid'
    prepared=client.post('/api/chain/contribution',json={'material':'wood','amount':1}).json()
    aid=prepared['actionId']
    assert client.get('/api/me').json()['player']['wood']==0
    with db.transaction() as connection:
        connection.execute('UPDATE chain_actions SET deadline=? WHERE action_id=?',(int(time.time())-100,aid))
    async def fake_rpc(url,method,params):
        assert method=='eth_call'
        return '0x0'  # on-chain actionId not yet used
    monkeypatch.setattr(mod,'rpc_call',fake_rpc)
    returned=client.post('/api/chain/cancel/'+aid)
    assert returned.status_code==200,returned.text
    assert returned.json()['status']=='expired'
    assert client.get('/api/me').json()['player']['wood']==1
    again=client.post('/api/chain/cancel/'+aid)
    assert again.status_code==200
    assert client.get('/api/me').json()['player']['wood']==1
    assert client.get('/api/chain/action/'+aid).json()['status']=='expired'
    assert client.post('/api/chain/submit',json={'action_id':aid,'tx_hash':'0x'+'00'*32}).status_code==409

def test_mocked_rpc_receipt_proves_correct_event_and_finalizes_once(client,player,monkeypatch):
    import importlib
    from app.crypto import keccak256,word,address_word
    mod=importlib.import_module('app.main')
    db=client.app.state.repo
    addr=address_from_private_key(1)
    msg=client.post('/api/identity/challenge',json={'address':addr}).json()['typedData']['message']
    assert client.post('/api/identity/verify',json={'address':addr,'signature':sign_digest(1,login_digest(addr,msg['nonce'],msg['expiresAt']))}).status_code==200
    db.position(player['id'],13,12)
    assert client.post('/api/gather',json={'node_id':'oak'}).status_code==200
    db.position(player['id'],27,12)
    cfg=client.app.state.config
    cfg.game_contract=address_from_private_key(5)
    cfg.oracle_private_key='0x'+'0'*63+'3'
    cfg.rpc_url='http://stub.invalid'
    voucher=client.post('/api/chain/contribution',json={'material':'wood','amount':1}).json()
    aid=voucher['actionId'];txhash='0x'+'77'*32
    assert client.post('/api/chain/submit',json={'action_id':aid,'tx_hash':txhash}).status_code==200
    topic='0x'+keccak256(b'Contributed(address,uint256,uint256,bytes32)').hex()
    receipt={'status':'0x1','to':cfg.game_contract,'blockNumber':'0x64',
             'logs':[{'address':cfg.game_contract,'topics':[topic,'0x'+address_word(addr).hex(),'0x'+word(1).hex()],
                      'data':'0x'+word(1).hex()+aid[2:]}]}
    async def fake_rpc(url,method,params):
        return {'eth_getTransactionReceipt':receipt,'eth_blockNumber':'0x70'}[method]
    monkeypatch.setattr(mod,'rpc_call',fake_rpc)
    first=client.get('/api/chain/action/'+aid)
    assert first.status_code==200,first.text
    assert first.json()['status']=='confirmed'
    assert client.get('/api/chain/action/'+aid).json()['status']=='confirmed'
    assert client.get('/api/me').json()['player']['wood']==0
    assert client.get('/api/world').json()['world']['bridge']['progress']==1
    scores=client.get('/api/leaderboard').json()['players']
    assert scores[0]['contributed']==1
    assert 'wallet' not in scores[0]
