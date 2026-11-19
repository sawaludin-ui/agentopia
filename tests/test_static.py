import re
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class IdParser(HTMLParser):
    def __init__(self):super().__init__();self.ids=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k=='id':self.ids.append(v)

def test_game_javascript_required_ids_exist():
    parser=IdParser();parser.feed((ROOT/'web/index.html').read_text())
    ids=set(parser.ids)
    assert len(parser.ids)==len(ids),'Duplicate HTML id(s) found'
    js=(ROOT/'web/game.js').read_text()
    # Only strict static selectors; dynamic modal IDs are constructed at runtime.
    dynamic={'materials','doDonate','doOnchain','donateAmount','pixText','pixClose',
             'newName','avatarChoices','saveProfile','joinContract','walletAddress',
             'getChallenge','identitySteps','typedPreview','copyTyped','signInjected',
             'walletSig','verifySig','txTo','txData','copyTx','sendTx',
             'hashArea','submittedTx','trackTx','txStatus'}
    mentioned=set(re.findall(r"\$\('([^']+)'\)",js))
    assert not (mentioned-ids-dynamic),f'Missing element ids: {mentioned-ids-dynamic}'

def test_solidity_contract_is_non_custodial():
    code=(ROOT/'contracts/src/AgentopiaCore.sol').read_text()
    assert 'function joinCity()' in code
    assert 'function contribute(' in code
    assert 'balanceOf(msg.sender)' in code
    assert 'usedActions[actionId] = true' in code
    for prohibited in ['delegatecall(','.transfer(','.send(','.call{value:', 'transferFrom(']:
        assert prohibited not in code

def test_no_remote_script_dependencies():
    html=(ROOT/'web/index.html').read_text()
    assert 'https://cdn.' not in html
    assert '<script src="/game.js"' in html
    assert 'type="password"' not in html
