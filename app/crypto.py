"""Minimal audited-by-tests? NO. Self-contained Ethereum keccak/secp256k1/EIP712
for local development. For production prefer established audited crypto libraries.
"""
import hashlib
import hmac

MASK = (1 << 64) - 1
RC = [0x1,0x8082,0x800000000000808a,0x8000000080008000,0x808b,
0x80000001,0x8000000080008081,0x8000000000008009,0x8a,
0x88,0x80008009,0x8000000a,0x8000808b,0x800000000000008b,
0x8000000000008089,0x8000000000008003,0x8000000000008002,
0x8000000000000080,0x800a,0x800000008000000a,0x8000000080008081,
0x8000000000008080,0x80000001,0x8000000080008008]
ROT = [[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]

def _rol(a,n):
    return ((a << n) | (a >> (64-n))) & MASK if n else a

def _keccakf(s):
    for rc in RC:
        c = [s[x]^s[x+5]^s[x+10]^s[x+15]^s[x+20] for x in range(5)]
        d = [c[(x-1)%5]^_rol(c[(x+1)%5],1) for x in range(5)]
        for y in range(5):
            for x in range(5): s[x+5*y] ^= d[x]
        b=[0]*25
        for x in range(5):
            for y in range(5): b[y+5*((2*x+3*y)%5)] = _rol(s[x+5*y],ROT[x][y])
        for y in range(5):
            for x in range(5): s[x+5*y] = b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y])
        s[0] ^= rc

def keccak256(data:bytes)->bytes:
    rate=136
    pad=bytearray(data); pad.append(1)
    while len(pad)%rate: pad.append(0)
    pad[-1]^=0x80
    st=[0]*25
    for k in range(0,len(pad),rate):
        block=pad[k:k+rate]
        for i in range(rate//8): st[i]^=int.from_bytes(block[8*i:8*i+8],'little')
        _keccakf(st)
    return b''.join(st[i].to_bytes(8,'little') for i in range(4))

P=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G=(55066263022277343669578718895168534326250603453777594175500187360389116729240,
32670510020758816978083085130507043184471273380659243275938904335757337482424)

def _add(p,q):
    if p is None: return q
    if q is None: return p
    x1,y1=p; x2,y2=q
    if x1==x2 and (y1+y2)%P==0: return None
    if p==q:
        if y1==0: return None
        l=(3*x1*x1*pow(2*y1,-1,P))%P
    else: l=((y2-y1)*pow((x2-x1)%P,-1,P))%P
    x=(l*l-x1-x2)%P
    return (x, (l*(x1-x)-y1)%P)

def _mul(k,p):
    if k==0 or p is None: return None
    if k<0: return _mul(-k,(p[0],(-p[1])%P))
    r=None
    while k:
        if k&1: r=_add(r,p)
        p=_add(p,p); k//=2
    return r

def _addr(point):
    if point is None: raise ValueError('Invalid point')
    return '0x'+keccak256(point[0].to_bytes(32,'big')+point[1].to_bytes(32,'big'))[-20:].hex()

def address_from_private_key(key:int)->str:
    if not 0<key<N: raise ValueError('Invalid key')
    return _addr(_mul(key,G))

def recover_address(digest:bytes,sig_hex:str)->str:
    if len(digest)!=32: raise ValueError('Digest length invalid')
    if not isinstance(sig_hex,str) or not sig_hex.startswith('0x') or len(sig_hex)!=132:
        raise ValueError('Signature must be 65 bytes')
    sig=bytes.fromhex(sig_hex[2:]); r=int.from_bytes(sig[:32],'big'); s=int.from_bytes(sig[32:64],'big'); v=sig[64]
    if not (1<=r<N and 1<=s<=N//2): raise ValueError('Non-canonical signature')
    if v in (27,28): v-=27
    if v not in (0,1): raise ValueError('Unsupported recovery id')
    x=r
    y2=(pow(x,3,P)+7)%P
    y=pow(y2,(P+1)//4,P)
    if (y*y)%P!=y2: raise ValueError('Invalid elliptic curve point')
    if y%2!=v: y=P-y
    R=(x,y)
    if _mul(N,R) is not None: raise ValueError('Invalid recovery point')
    z=int.from_bytes(digest,'big')
    q=_mul(pow(r,-1,N),_add(_mul(s,R),_mul((-z)%N,G)))
    return _addr(q)

def sign_digest(private_key:int,digest:bytes)->str:
    if not 0<private_key<N or len(digest)!=32: raise ValueError('Invalid signing key/digest')
    x=private_key.to_bytes(32,'big')
    # Deterministic RFC6979 HMAC-SHA256 nonce. Never use sample keys for real assets.
    v=b'\x01'*32; k=b'\x00'*32
    k=hmac.new(k,v+b'\x00'+x+digest,hashlib.sha256).digest()
    v=hmac.new(k,v,hashlib.sha256).digest()
    k=hmac.new(k,v+b'\x01'+x+digest,hashlib.sha256).digest()
    v=hmac.new(k,v,hashlib.sha256).digest()
    while True:
        v=hmac.new(k,v,hashlib.sha256).digest(); nonce=int.from_bytes(v,'big')
        if 1<=nonce<N:
            pt=_mul(nonce,G); r=pt[0]%N
            if r:
                s=(pow(nonce,-1,N)*(int.from_bytes(digest,'big')+r*private_key))%N
                if s:
                    rec=pt[1]&1
                    if s>N//2: s=N-s; rec^=1
                    if pt[0]>=N: raise ValueError('Recovery id 2/3 not supported')
                    return '0x'+r.to_bytes(32,'big').hex()+s.to_bytes(32,'big').hex()+bytes([rec+27]).hex()
        k=hmac.new(k,v+b'\x00',hashlib.sha256).digest()
        v=hmac.new(k,v,hashlib.sha256).digest()

def word(n:int)->bytes:
    if not isinstance(n,int) or not 0<=n<2**256: raise ValueError('uint256 out of range')
    return n.to_bytes(32,'big')

def address_word(addr:str)->bytes:
    if len(addr)!=42 or not addr.startswith('0x'):
        raise ValueError('Address invalid')
    try: raw=bytes.fromhex(addr[2:])
    except ValueError as e: raise ValueError('Address invalid') from e
    if len(raw)!=20: raise ValueError('Address invalid')
    return bytes(12)+raw

def _domain(name:str,version:str,chain_id:int,contract:str|None=None)->bytes:
    if contract is None:
        h=keccak256(b'EIP712Domain(string name,string version,uint256 chainId)')
        return keccak256(h+keccak256(name.encode())+keccak256(version.encode())+word(chain_id))
    h=keccak256(b'EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)')
    return keccak256(h+keccak256(name.encode())+keccak256(version.encode())+word(chain_id)+address_word(contract))

def login_digest(addr:str,nonce:str,expires_at:int,chain_id:int=56)->bytes:
    typ=keccak256(b'AgentopiaLogin(address wallet,string nonce,uint256 chainId,uint256 expiresAt)')
    struct=keccak256(typ+address_word(addr)+keccak256(nonce.encode())+word(chain_id)+word(expires_at))
    return keccak256(b'\x19\x01'+_domain('Agentopia','1',chain_id)+struct)

def login_typed_data(addr:str,nonce:str,expires_at:int,chain_id:int=56)->dict:
    return {'types':{'EIP712Domain':[{'name':'name','type':'string'},{'name':'version','type':'string'},{'name':'chainId','type':'uint256'}],
                     'AgentopiaLogin':[{'name':'wallet','type':'address'},{'name':'nonce','type':'string'},{'name':'chainId','type':'uint256'},{'name':'expiresAt','type':'uint256'}]},
            'domain':{'name':'Agentopia','version':'1','chainId':chain_id},'primaryType':'AgentopiaLogin',
            'message':{'wallet':addr,'nonce':nonce,'chainId':chain_id,'expiresAt':expires_at}}

def contribution_digest(addr:str,building_id:int,amount:int,action_id:bytes,deadline:int,contract:str,chain_id:int=56)->bytes:
    if len(action_id)!=32: raise ValueError('Action ID length invalid')
    typ=keccak256(b'Contribution(address player,uint256 buildingId,uint256 amount,bytes32 actionId,uint256 deadline)')
    struct=keccak256(typ+address_word(addr)+word(building_id)+word(amount)+action_id+word(deadline))
    return keccak256(b'\x19\x01'+_domain('Agentopia','1',chain_id,contract)+struct)

def calldata_join()->str:
    return '0x'+keccak256(b'joinCity()')[:4].hex()

def calldata_contribute(building_id:int,amount:int,action_id:bytes,deadline:int,signature:str)->str:
    sig=bytes.fromhex(signature.removeprefix('0x'))
    if len(sig)!=65: raise ValueError('Signature invalid')
    selector=keccak256(b'contribute(uint256,uint256,bytes32,uint256,bytes)')[:4]
    dynamic=word(len(sig))+sig+b'\x00'*((32-len(sig)%32)%32)
    return '0x'+(selector+word(building_id)+word(amount)+action_id+word(deadline)+word(5*32)+dynamic).hex()

def contribution_typed_data(addr:str,building_id:int,amount:int,action_id:bytes,deadline:int,contract:str,chain_id:int=56)->dict:
    if len(action_id)!=32:raise ValueError('Action ID length invalid')
    return {'types':{
        'EIP712Domain':[{'name':'name','type':'string'},{'name':'version','type':'string'},{'name':'chainId','type':'uint256'},{'name':'verifyingContract','type':'address'}],
        'Contribution':[{'name':'player','type':'address'},{'name':'buildingId','type':'uint256'},{'name':'amount','type':'uint256'},{'name':'actionId','type':'bytes32'},{'name':'deadline','type':'uint256'}]},
        'domain':{'name':'Agentopia','version':'1','chainId':chain_id,'verifyingContract':contract},
        'primaryType':'Contribution',
        'message':{'player':addr,'buildingId':building_id,'amount':amount,'actionId':'0x'+action_id.hex(),'deadline':deadline}}
