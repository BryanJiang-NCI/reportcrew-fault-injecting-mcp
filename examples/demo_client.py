import argparse
import asyncio
import time
from mcp_chaos_proxy.server import client

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000/mcp/')
    parser.add_argument('--expression', default='20 * 5')
    parser.add_argument('--tool', choices=['calculator', 'web_search', 'fetch_page'], default='calculator')
    parser.add_argument('--query', default='annual report')
    parser.add_argument('--page-url', default='https://example.com/alpha-report')
    args = parser.parse_args()
    async with client(args.url) as session:
        print('Tools:', [t.name for t in (await session.list_tools()).tools])
        start = time.monotonic()
        arguments = {'calculator': {'expression': args.expression}, 'web_search': {'query': args.query}, 'fetch_page': {'url': args.page_url}}
        result = await session.call_tool(args.tool, arguments[args.tool])
        print('Elapsed seconds:', round(time.monotonic() - start, 3))
        print(result.model_dump_json(exclude_none=True))

asyncio.run(main())
