import json
import time
import pytest
from mcp.types import CallToolResult, TextContent
from mcp_chaos_proxy.engine import Engine, load_config
from mcp_chaos_proxy.server import calculate

def policy(kind, params, probability=1, tool='calculator'):
    return dict(tool=tool, type=kind, parameters=params, probability=probability, enabled=True)

def make(tmp_path, faults): return Engine({'seed':42, 'faults':faults}, tmp_path/'log')

async def upstream(): return CallToolResult(content=[TextContent(type='text', text='{"result": 100}')], structuredContent={'result':100}, isError=False)

async def test_faults(tmp_path):
    e=make(tmp_path,[policy('latency',{'delay_ms':50}),policy('offset',{'offset':5})])
    start=time.monotonic(); result=await e.invoke('calculator',upstream)
    assert time.monotonic()-start >= .05 and result.structuredContent['result']==105 and not result.isError
    assert [json.loads(x)['fault_type'] for x in (tmp_path/'log').read_text().splitlines()]==['latency','offset']
    e=make(tmp_path,[policy('error',{'message':'failure'})])
    assert (await e.invoke('calculator',upstream)).isError

async def test_creates_log_directory(tmp_path):
    log_path = tmp_path / 'experiments' / 'run1' / 'faults.jsonl'
    engine = Engine({'seed': 42, 'faults': [policy('error', {'message': 'failure'})]}, log_path)
    assert log_path.parent.is_dir()
    assert (await engine.invoke('calculator', upstream)).isError
    assert json.loads(log_path.read_text())['fault_type'] == 'error'

async def test_matching_and_probability(tmp_path):
    e=make(tmp_path,[policy('error',{'message':'x'},0),policy('error',{'message':'x'},1,'other')])
    assert (await e.invoke('calculator',upstream)).structuredContent['result']==100
    a=make(tmp_path,[policy('error',{'message':'x'},.5)])
    b=make(tmp_path,[policy('error',{'message':'x'},.5)])
    assert [bool(a.select('calculator')) for _ in range(30)] == [bool(b.select('calculator')) for _ in range(30)]

@pytest.mark.parametrize('config',[{}, {'seed':1,'faults':[policy('latency',{'delay_ms':-1})]}, {'seed':1,'faults':[policy('offset',{'offset':True})]}, {'seed':1,'faults':[policy('error',{'message':'x'},2)]}])
def test_invalid(tmp_path,config):
    path=tmp_path/'c.json'; path.write_text(json.dumps(config))
    with pytest.raises(ValueError): load_config(path)

def test_calculator():
    assert calculate('20 * 5')==100
    with pytest.raises(ValueError): calculate('__import__("os")')

def test_local_web_fixtures():
    from mcp_chaos_proxy.server import search, fetch
    hits = search('alpha annual')
    assert len(hits) == 1
    assert fetch(hits[0]['url'])['status'] == 200
    assert fetch('https://example.com/missing')['status'] == 404
    assert search('no-such-document') == []
