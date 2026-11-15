import asyncio
import json
import math
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path


def load_config(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or type(data.get('seed')) is not int or not isinstance(data.get('faults'), list):
        raise ValueError('Expected integer seed and faults list')
    for p in data['faults']:
        if not isinstance(p, dict) or not isinstance(p.get('tool'), str) or not p['tool'] or type(p.get('enabled')) is not bool:
            raise ValueError('Invalid tool or enabled')
        probability = p.get('probability')
        if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError('Invalid probability')
        params = p.get('parameters')
        if not isinstance(params, dict) or p.get('type') not in ('latency', 'error', 'offset'):
            raise ValueError('Invalid fault type or parameters')
        if p['type'] == 'latency' and (type(params.get('delay_ms')) not in (int, float) or not math.isfinite(params['delay_ms']) or params['delay_ms'] < 0):
            raise ValueError('Invalid delay_ms')
        if p['type'] == 'error' and (not isinstance(params.get('message'), str) or not params['message']):
            raise ValueError('Invalid error message')
        if p['type'] == 'offset' and (type(params.get('offset')) not in (int, float) or not math.isfinite(params['offset'])):
            raise ValueError('Invalid offset')
    return data


class Engine:
    def __init__(self, config, log_path):
        self.config, self.log_path = config, Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.random = random.Random(config['seed'])

    def select(self, tool):
        return [p for p in self.config['faults'] if p['enabled'] and p['tool'] == tool and self.random.random() < p['probability']]

    def log(self, invocation, tool, policy, **details):
        event = dict(timestamp=datetime.now(timezone.utc).isoformat(), invocation_id=invocation, tool=tool, fault_type=policy['type'], parameters=policy['parameters'], injected=True, **details)
        with self.log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(event, allow_nan=False) + '\n')

    async def invoke(self, tool, upstream):
        from mcp.types import CallToolResult, TextContent
        invocation = uuid.uuid4().hex
        selected = self.select(tool)
        for p in selected:
            if p['type'] == 'latency':
                self.log(invocation, tool, p)
                await asyncio.sleep(p['parameters']['delay_ms'] / 1000)
            elif p['type'] == 'error':
                self.log(invocation, tool, p, error=p['parameters']['message'])
                return CallToolResult(content=[TextContent(type='text', text=p['parameters']['message'])], isError=True)
        result = await upstream()
        for p in selected:
            if p['type'] != 'offset' or result.isError:
                continue
            # Only the explicitly supported calculator representation is safe to alter.
            structured = result.structuredContent
            if tool != 'calculator' or not structured or type(structured.get('result')) not in (int, float):
                continue
            original = structured['result']
            modified = original + p['parameters']['offset']
            if not math.isfinite(modified):
                continue
            updated = dict(structured, result=modified)
            result = result.model_copy(update={'structuredContent': updated, 'content': [TextContent(type='text', text=json.dumps(updated))]})
            self.log(invocation, tool, p, original_result=original, modified_result=modified)
        return result
