import pytest
from app.crypto import (keccak256,address_from_private_key,login_digest,login_typed_data,
                        recover_address,sign_digest,contribution_digest,calldata_join,calldata_contribute)

def test_keccak_known_vectors():
    assert keccak256(b'').hex()=='c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470'
    assert keccak256(b'abc').hex()=='4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45'

def test_known_wallet_address():
    assert address_from_private_key(1)=='0x7e5f4552091a69125d5dfcb7b8c2659029395bdf'

def test_sign_recover_and_signature_binding():
    addr=address_from_private_key(1)
    digest=login_digest(addr,'unique-challenge',1790000000,56)
    sig=sign_digest(1,digest)
    assert recover_address(digest,sig)==addr
    assert recover_address(login_digest(addr,'wrong',1790000000,56),sig)!=addr
    assert recover_address(login_digest(addr,'unique-challenge',1790000000,97),sig)!=addr
    assert sig==sign_digest(1,digest)

@pytest.mark.parametrize('signature', ['0x0','ff','0x'+'00'*65,'0x'+'ff'*65])
def test_signature_invalid(signature):
    with pytest.raises(ValueError):recover_address(b'0'*32,signature)

def test_contribution_hash_and_calldata():
    addr=address_from_private_key(3);contract=address_from_private_key(5)
    action=bytes.fromhex('12'*32)
    d=contribution_digest(addr,1,10,action,1790000000,contract,56)
    sig=sign_digest(3,d)
    assert recover_address(d,sig)==addr
    assert d!=contribution_digest(addr,1,10,action,1790000000,contract,97)
    assert d!=contribution_digest(addr,1,11,action,1790000000,contract,56)
    calldata=calldata_contribute(1,10,action,1790000000,sig)
    assert calldata.startswith('0x') and len(calldata)>400
    assert calldata_join()=='0xcb245cbf'

def test_eip712_data_shape():
    data=login_typed_data(address_from_private_key(1),'abc',1800000000)
    assert data['primaryType']=='AgentopiaLogin'
    assert data['message']['nonce']=='abc'
    assert data['domain']['chainId']==56

def test_signature_compatible_with_independent_crypto_backend():
    from cryptography.hazmat.primitives.asymmetric import ec,utils
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature
    digest=keccak256(b'crypto independent crosscheck')
    sig=bytes.fromhex(sign_digest(7,digest)[2:])
    der=utils.encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:64],'big'))
    ec.derive_private_key(7,ec.SECP256K1()).public_key().verify(der,digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
