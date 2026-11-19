#!/usr/bin/env python3
"""BNB Chain testnet deployment runner, CLI keystore only.

No private key is read, logged, or accepted as a command-line argument.
Use a DISPOSABLE keystore, not a personal wallet. The script refuses any
chain except BSC Testnet (97), and requires explicit --broadcast to transact.

Example (requires Foundry, forge-std, test tBNB):
python scripts/testnet_deploy.py --account agentopia-test-deployer \
    --oracle 0xYOUR_TEST_ORACLE_ADDRESS --broadcast
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / 'contracts'
DEFAULT_RPC = 'https://data-seed-prebsc-1-s1.bnbchain.org:8545'
ADDRESS_RE = re.compile(r'0x[a-fA-F0-9]{40}$')


def rpc_call(url: str, method: str, params: list, timeout: int = 8):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 5, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(url, payload, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('error') or 'result' not in result:
        raise RuntimeError(f'RPC response invalid for {method}: {str(result)[:160]}')
    return result['result']


def run(args: list[str], cwd: Path = CONTRACTS) -> str:
    # CLI keystore handles signing internally; never print raw private keys.
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"Command failed: {args[0]} {args[1] if len(args) > 1 else ''}: "
                           f"{(proc.stderr or proc.stdout)[-550:]}")
    return proc.stdout.strip()


def parse_deployed(output: str) -> dict:
    try:
        # Recent forge versions can emit pretty-printed JSON.
        record = json.loads(output)
        if isinstance(record, list):
            record = record[-1]
    except (ValueError, IndexError):
        try:
            # Some versions include logs around the JSON object.
            record = json.loads(output[output.index('{'):output.rindex('}') + 1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError('Cannot parse Forge deployment JSON; inspect output locally') from exc
    if not isinstance(record, dict):
        raise RuntimeError('Forge returned unexpected deployment data')
    address = record.get('deployedTo') or record.get('deployed_to')
    tx_hash = record.get('transactionHash') or record.get('transaction_hash')
    if not (isinstance(address, str) and ADDRESS_RE.fullmatch(address)):
        raise RuntimeError('Forge did not report a valid deployed address')
    if not (isinstance(tx_hash, str) and re.fullmatch(r'0x[a-fA-F0-9]{64}', tx_hash)):
        raise RuntimeError('Forge did not report a valid deployment tx hash')
    return {'address': address, 'tx_hash': tx_hash}


def forge_create(contract: str, rpc: str, account: str, constructor_args: list[str] | None = None):
    cmd = ['forge', 'create', contract, '--rpc-url', rpc, '--account', account, '--broadcast', '--json']
    if constructor_args:
        cmd += ['--constructor-args'] + constructor_args
    return parse_deployed(run(cmd))


def assert_balance_positive(balance_hex: str):
    if int(balance_hex, 16) <= 0:
        raise RuntimeError('Test deployer has zero tBNB; testnet faucet funding required')


def preflight(rpc: str, account: str | None):
    checks = {'chainId': None, 'blockNumber': None, 'foundry': {}, 'wallet': None, 'balanceWei': None}
    failures = []
    for exe in ('forge', 'cast'):
        checks['foundry'][exe] = bool(shutil.which(exe))
        if not checks['foundry'][exe]: failures.append(f'{exe}: not installed')
    try:
        chain = int(rpc_call(rpc, 'eth_chainId', []), 16)
        checks['chainId'] = chain
        if chain != 97:
            failures.append(f'RPC is chain {chain}, expected BSC Testnet 97; deployment forbidden')
        else:
            checks['blockNumber'] = int(rpc_call(rpc, 'eth_blockNumber', []), 16)
    except Exception as exc:
        failures.append(f'RPC unavailable: {type(exc).__name__}: {str(exc)[:150]}')
    if checks['foundry']['cast'] and account:
        try:
            address = run(['cast', 'wallet', 'address', '--account', account])
            if not ADDRESS_RE.fullmatch(address):
                raise RuntimeError('No valid address returned by cast wallet')
            checks['wallet'] = address
            if checks['chainId'] == 97:
                bal = rpc_call(rpc, 'eth_getBalance', [address, 'latest'])
                checks['balanceWei'] = int(bal, 16)
                assert_balance_positive(bal)
        except Exception as exc:
            failures.append(f'Test keystore or gas issue: {type(exc).__name__}: {str(exc)[:180]}')
    elif account:
        failures.append('Test wallet cannot be read without cast')
    return checks, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rpc', default=DEFAULT_RPC, help='BSC Testnet JSON-RPC endpoint')
    parser.add_argument('--account', default='agentopia-test-deployer', help='Encrypted Foundry keystore name')
    parser.add_argument('--oracle', help='Test oracle address; never pass a private key here')
    parser.add_argument('--broadcast', action='store_true', help='Explicitly authorize TESTNET transactions')
    parser.add_argument('--report', default=str(ROOT / 'artifacts' / 'testnet-deployment-attempt.json'))
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'generatedAtUTC': dt.datetime.now(dt.timezone.utc).isoformat(),
              'target': 'BSC Testnet', 'expectedChainId': 97,
              'rpc': args.rpc, 'broadcastRequested': args.broadcast,
              'status': 'PREFLIGHT', 'preflight': {}, 'failures': [], 'deployments': {}}
    try:
        checks, failures = preflight(args.rpc, args.account)
        report['preflight'] = checks
        report['failures'] += failures
        if failures:
            report['status'] = 'BLOCKED'
            return 2
        if not args.broadcast:
            report['status'] = 'PREFLIGHT_PASS_NO_BROADCAST'
            return 0
        if not (args.oracle and ADDRESS_RE.fullmatch(args.oracle) and int(args.oracle, 16) > 0):
            report['status'] = 'BLOCKED'
            report['failures'].append('Provide a valid test-only oracle address via --oracle')
            return 2
        # Dependency test first; do not deploy if Solidity cannot compile/test.
        run(['forge', 'build'])
        run(['forge', 'test', '-vv'])
        mock = forge_create('src/MockAgentID.sol:MockAgentID', args.rpc, args.account)
        report['deployments']['MockAgentID'] = mock
        # Persist the mock even if a later transaction fails.
        report_path.write_text(json.dumps(report, indent=2))
        # Only AFTER the mock's receipt exists, deploy core.
        core = forge_create('src/AgentopiaCore.sol:AgentopiaCore', args.rpc,
                            args.account, [mock['address'], args.oracle])
        report['deployments']['AgentopiaCore'] = core
        report_path.write_text(json.dumps(report, indent=2))
        # Grant mock ownership to deployer; don't treat mock as official Agent ID.
        run(['cast', 'send', mock['address'], 'grant(address)', checks['wallet'],
             '--rpc-url', args.rpc, '--account', args.account])
        holder_count = run(['cast', 'call', mock['address'], 'balanceOf(address)(uint256)',
                            checks['wallet'], '--rpc-url', args.rpc])
        if int(holder_count.split()[0], 0) != 1:
            raise RuntimeError('Mock holder grant verification failed')
        run(['cast', 'send', core['address'], 'joinCity()',
             '--rpc-url', args.rpc, '--account', args.account])
        joined = run(['cast', 'call', core['address'], 'citizens(address)(bool)',
                      checks['wallet'], '--rpc-url', args.rpc])
        if 'true' not in joined.lower() and joined.strip() not in ('1', '0x1'):
            raise RuntimeError('On-chain citizenship verification failed')
        report['status'] = 'TESTNET_JOIN_VERIFIED'
        report['testnetExplorer'] = f"https://testnet.bscscan.com/address/{core['address']}"
        return 0
    except Exception as exc:
        report['status'] = 'FAILED'
        report['failures'].append(f'{type(exc).__name__}: {str(exc)[:350]}')
        return 1
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    sys.exit(main())
