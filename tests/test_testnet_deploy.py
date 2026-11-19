"""Offline tests for the guarded BSC Testnet deploy runner.
These do NOT prove a transaction was broadcast.
"""
from unittest.mock import patch
import pytest
from scripts import testnet_deploy as d

ADDR='0x'+'a'*40
TX='0x'+'b'*64


def test_parse_deployed():
    assert d.parse_deployed('{"deployedTo":"'+ADDR+'","transactionHash":"'+TX+'"}') == {'address':ADDR,'tx_hash':TX}


def test_parse_deployed_rejects_missing_transaction_hash():
    with pytest.raises(RuntimeError, match='tx hash'):
        d.parse_deployed('{"deployedTo":"'+ADDR+'"}')


def test_parse_deployed_rejects_bad_address():
    with pytest.raises(RuntimeError, match='address'):
        d.parse_deployed('{"deployedTo":"0x123","transactionHash":"'+TX+'"}')


def test_preflight_wrong_chain_refuses():
    with patch.object(d.shutil,'which',return_value=None), patch.object(d,'rpc_call',return_value='0x38'):
        check,fail = d.preflight('https://example.invalid',None)
    assert check['chainId']==56
    assert any('deployment forbidden' in msg for msg in fail)


def test_preflight_blocked_rpc():
    with patch.object(d.shutil,'which',return_value=None), patch.object(d,'rpc_call',side_effect=OSError('no dns')):
        check,fail = d.preflight('https://example.invalid',None)
    assert check['chainId'] is None
    assert any('RPC unavailable' in msg for msg in fail)


def test_zero_balance_refused():
    with pytest.raises(RuntimeError,match='zero tBNB'):
        d.assert_balance_positive('0x0')


def test_preflight_accepts_valid_chain_and_funded_wallet():
    rpc_returns={'eth_chainId':'0x61','eth_blockNumber':'0x123','eth_getBalance':'0xde0b6b3a7640000'}
    with patch.object(d.shutil,'which',return_value='/usr/bin/fake'), \
         patch.object(d,'rpc_call',side_effect=lambda url,method,params: rpc_returns[method]), \
         patch.object(d,'run',return_value=ADDR):
        check,fail=d.preflight('https://example.invalid','test-key')
    assert fail==[]
    assert check['chainId']==97 and check['wallet']==ADDR and check['balanceWei']==10**18
