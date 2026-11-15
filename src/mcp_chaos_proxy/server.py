import argparse
import ast
import operator
from contextlib import asynccontextmanager
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn
from .engine import Engine, load_config

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}

# Fictional, local documents: these are not live web results or financial facts.
PAGES = {
    'https://example.com/alpha-report': {'title': 'Alpha annual report', 'text': 'Fictional Alpha revenue: 100 million.'},
    'https://example.com/beta-report': {'title': 'Beta annual report', 'text': 'Fictional Beta revenue: 80 million.'},
}

def search(query):
    terms = query.casefold().split()
    return [{'title': page['title'], 'url': url} for url, page in PAGES.items()
            if all(term in (page['title'] + ' ' + page['text']).casefold() for term in terms)]

def fetch(url):
    page = PAGES.get(url)
    return {'status': 200 if page else 404, 'headers': {'content-type': 'text/plain; charset=utf-8'},
            'text': page['text'] if page else 'Not found in local fixture corpus.'}

def calculate(expression):
    if len(expression) > 200:
        raise ValueError('Expression too long')
    def visit(node, depth=0):
        if depth > 30: raise ValueError('Expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float): return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS: return OPS[type(node.op)](visit(node.left, depth+1), visit(node.right, depth+1))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS: return OPS[type(node.op)](visit(node.operand, depth+1))
        raise ValueError('Unsupported expression')
    result = visit(ast.parse(expression, mode='eval').body)
    if not (-1e100 < result < 1e100): raise ValueError('Result out of range')
    return result

def toy():
    server = Server('toy-reportcrew-tools')
    @server.list_tools()
    async def list_tools():
        return [types.Tool(name='calculator', description='Evaluate arithmetic', inputSchema={'type':'object','properties':{'expression':{'type':'string'}},'required':['expression']}, outputSchema={'type':'object','properties':{'result':{'type':'number'}},'required':['result']}),
                types.Tool(name='web_search', description='Search fictional local documents, not the live web', inputSchema={'type':'object','properties':{'query':{'type':'string'}},'required':['query']}),
                types.Tool(name='fetch_page', description='Read a fictional local document, not a live URL', inputSchema={'type':'object','properties':{'url':{'type':'string'}},'required':['url']})]
    @server.call_tool()
    async def call(name, args):
        if name == 'calculator': return {'result': calculate(args['expression'])}
        if name == 'web_search': return {'hits': search(args['query'])}
        if name == 'fetch_page': return fetch(args['url'])
        raise ValueError('Unknown tool')
    return server

@asynccontextmanager
async def client(url):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session

def proxy(url, engine):
    server = Server('chaos-proxy')
    @server.list_tools()
    async def list_tools():
        async with client(url) as session:
            return (await session.list_tools()).tools
    @server.call_tool(validate_input=False)
    async def call(name, args):
        async def upstream():
            async with client(url) as session:
                return await session.call_tool(name, args)
        return await engine.invoke(name, upstream)
    return server

def app_for(server):
    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)
    @asynccontextmanager
    async def lifespan(app):
        async with manager.run(): yield
    async def handle(scope, receive, send):
        await manager.handle_request(scope, receive, send)
    return Starlette(routes=[Mount('/mcp', app=handle)], lifespan=lifespan)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['toy','proxy'])
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--upstream', default='http://127.0.0.1:8001/mcp/')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--log', default='faults.jsonl')
    args = parser.parse_args()
    server = toy() if args.mode == 'toy' else proxy(args.upstream, Engine(load_config(args.config), args.log))
    uvicorn.run(app_for(server), host='127.0.0.1', port=args.port)

if __name__ == '__main__': main()
