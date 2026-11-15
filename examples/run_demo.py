"""Runs real HTTP processes and records observed client output and fault events."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from mcp_chaos_proxy.server import client

ROOT=Path(__file__).resolve().parents[1]
ENV=dict(os.environ, PYTHONPATH=str(ROOT/'src'))
async def call(port, tool='calculator', arguments=None):
    async with client(f'http://127.0.0.1:{port}/mcp/') as session:
        assert 'calculator' in [t.name for t in (await session.list_tools()).tools]
        start=time.monotonic()
        result=await session.call_tool(tool, arguments if arguments is not None else {'expression':'20 * 5'})
        return result, time.monotonic()-start

def start(*args):
    p=subprocess.Popen([sys.executable,'-m','mcp_chaos_proxy.server',*args],env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    if p.poll() is not None: raise RuntimeError('server failed to start')
    return p

def stop(p):
    p.terminate(); p.wait(timeout=10)

async def main():
    out=[]
    log=ROOT/'logs'/'faults.jsonl'
    log.unlink(missing_ok=True)
    toy=start('toy','--port','18001')
    try:
        direct,_=await call(18001)
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('normal','latency','error','offset'):
                params={'latency':{'delay_ms':250},'error':{'message':'Simulated upstream tool failure'},'offset':{'offset':5}}
                config={'seed':42,'faults':[] if kind=='normal' else [dict(tool='calculator',type=kind,enabled=True,probability=1.0,parameters=params[kind])]}
                path=Path(tmp)/'config.json'; path.write_text(json.dumps(config))
                proxy=start('proxy','--port','18000','--upstream','http://127.0.0.1:18001/mcp/','--config',str(path),'--log',str(log))
                try:
                    result,elapsed=await call(18000)
                    if kind=='normal':
                        for tool, args in [('web_search', {'query':'alpha'}), ('fetch_page', {'url':'https://example.com/alpha-report'})]:
                            expected, _ = await call(18001, tool, args)
                            forwarded, _ = await call(18000, tool, args)
                            assert forwarded == expected and not forwarded.isError
                            out.append(json.dumps({'scenario': 'normal_'+tool, 'result': forwarded.model_dump(exclude_none=True)}))
                finally: stop(proxy)
                if kind=='normal': assert result == direct
                if kind=='latency': assert result == direct and elapsed >= .25
                if kind=='error': assert result.isError and 'Simulated upstream' in result.content[0].text
                if kind=='offset': assert not result.isError and result.structuredContent['result']==105
                out.append(json.dumps({'scenario':kind,'elapsed_seconds':round(elapsed,3),'result':result.model_dump(exclude_none=True)}))
    finally: stop(toy)
    (ROOT/'logs'/'results.jsonl').write_text('\n'.join(out)+'\n')
    print('\n'.join(out))

asyncio.run(main())
