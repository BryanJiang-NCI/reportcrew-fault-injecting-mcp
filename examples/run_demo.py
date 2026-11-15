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
        assert tool in [t.name for t in (await session.list_tools()).tools]
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
        tools = {'calculator': {'expression': '20 * 5'},
                 'web_search': {'query': 'alpha'},
                 'fetch_page': {'url': 'https://example.com/alpha-report'}}
        direct = {tool: (await call(18001, tool, args))[0] for tool, args in tools.items()}
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('normal','latency','error','offset'):
                params={'latency':{'delay_ms':250},'error':{'message':'Simulated upstream tool failure'},'offset':{'offset':5}}
                selected_tools = ['calculator'] if kind == 'offset' else list(tools)
                config={'seed':42,'faults':[] if kind=='normal' else [dict(tool=tool,type=kind,enabled=True,probability=1.0,parameters=params[kind]) for tool in selected_tools]}
                path=Path(tmp)/'config.json'; path.write_text(json.dumps(config))
                proxy=start('proxy','--port','18000','--upstream','http://127.0.0.1:18001/mcp/','--config',str(path),'--log',str(log))
                try:
                    for tool in selected_tools:
                        result,elapsed=await call(18000, tool, tools[tool])
                        if kind=='normal': assert result == direct[tool] and not result.isError
                        if kind=='latency': assert result == direct[tool] and elapsed >= .25
                        if kind=='error': assert result.isError and 'Simulated upstream' in result.content[0].text
                        if kind=='offset': assert not result.isError and result.structuredContent['result']==105
                        out.append(json.dumps({'scenario':kind,'tool':tool,'elapsed_seconds':round(elapsed,3),'result':result.model_dump(exclude_none=True)}))
                finally: stop(proxy)
    finally: stop(toy)
    (ROOT/'logs'/'results.jsonl').write_text('\n'.join(out)+'\n')
    print('\n'.join(out))

asyncio.run(main())
