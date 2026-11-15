# MCP Chaos Proxy

## Overview

A minimal fault-injecting MCP proxy for exploring how tool failures affect tool-using systems. It forwards tool discovery and calls to an upstream MCP server and can inject latency, tool errors, and plausible incorrect calculator results. It runs locally without an LLM, API key, or paid service.

![Conceptual ReportCrew architecture with an MCP fault-injection proxy](PHD-Assignment-MCP-Proxy.png)

The diagram illustrates the **conceptual ReportCrew scenario**, including agents and separate web and math servers. This repository implements the standalone proxy and a demo client, not the agents or orchestrator. Its demo uses one toy MCP server exposing all three tools; the proxy connects to one upstream server at a time.

## Project Structure

```text
src/mcp_chaos_proxy/
  server.py       MCP proxy, toy server, and HTTP transport
  engine.py       Fault configuration, decisions, injection, and logging
examples/
  demo_client.py  Client for direct or proxied tool calls
  run_demo.py     End-to-end demonstration of the four scenarios
tests/            Automated tests
logs/             Captured demo results and fault events (JSONL)
config.json       Fault policies and random seed
pyproject.toml    Project metadata and dependencies
```

## Getting Started

Python 3.11 or newer is required. The project was tested with Python 3.13.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

Start the toy server in one terminal:

```sh
python -m mcp_chaos_proxy.server toy --port 8001
```

In a second terminal, activate the same virtual environment and start the proxy:

```sh
python -m mcp_chaos_proxy.server proxy --port 8000 --config config.json --log faults.jsonl
```

In a third activated terminal, call the calculator through the proxy:

```sh
python examples/demo_client.py --tool calculator --expression '20 * 5'
```

With the default configuration all faults are disabled, so the result is `100`. The proxy listens on port 8000 and forwards calls to the toy server on port 8001.

## Configuration

Edit `config.json` to select a tool, fault type, probability, enabled state, and parameters. For example, this configuration always adds a two-second delay to calculator calls:

```json
{
  "seed": 42,
  "faults": [
    {
      "tool": "calculator",
      "type": "latency",
      "probability": 1.0,
      "enabled": true,
      "parameters": {"delay_ms": 2000}
    }
  ]
}
```

The proxy reads the file at startup; **restart it after editing**. Probability must be between 0 and 1. The supported types are:

- `latency`: `delay_ms` is nonnegative; the call continues after the delay.
- `error`: `message` is returned as an MCP tool error (`isError=true`); upstream is not called.
- `offset`: `offset` is added to a successful calculator result. Both the structured result and its text representation are updated, while the call remains successful.

Latency and error can target any of the toy server's three tools. Offset applies only to `calculator`. Injected events are appended to the configured JSONL log; timestamps are UTC. Do not put secrets in policy parameters or error messages because these can appear in the log.

## Demo and Tests

To establish a baseline, start the toy server and call it **directly**, without the proxy:

```sh
python examples/demo_client.py --url http://127.0.0.1:8001/mcp/ --tool calculator --expression '20 * 5'
python examples/demo_client.py --url http://127.0.0.1:8001/mcp/ --tool web_search --query alpha
python examples/demo_client.py --url http://127.0.0.1:8001/mcp/ --tool fetch_page --page-url https://example.com/alpha-report
```

The calculator returns 100; search finds the fictional Alpha report; fetching that fixture returns status 200 and its text. To compare through the proxy, start it with all faults disabled and run the same commands without `--url`; the client defaults to port 8000.

Run all four scenarios and the unit tests:

```sh
python examples/run_demo.py
pytest -q
```

The demo starts temporary servers on ports 18000 and 18001, asserts normal forwarding and each fault, and overwrites [logs/results.jsonl](logs/results.jsonl) and [logs/faults.jsonl](logs/faults.jsonl) with its observations. The included files are from an actual run. Ensure those ports are free before running it. The results show the client responses; the fault log records each injection, including the original and modified values for the offset.

## Design Choices

- **Streamable HTTP and the official SDK:** the client, proxy, and toy server communicate locally using MCP Python SDK 1.26.0. The proxy reconstructs SDK messages rather than forwarding bytes unchanged.
- **Policy-driven injection:** JSON policies select a tool, fault and probability. The engine applies latency and errors before the upstream call and offsets after a successful result. Multiple selected policies run in configuration order; an injected error short-circuits execution.
- **Reproducibility:** each matching enabled policy consumes a pseudorandom draw, including probabilities zero and one. The same seed, configuration, sequential call order and process lifetime reproduce decisions. Timestamps, IDs and durations vary; this does not make LLM behavior deterministic.
- **Local fixtures:** `web_search(query)` and `fetch_page(url)` use a tiny fictional corpus; `example.com` URLs are identifiers, not HTTP requests or real financial reports. Unknown fixture URLs return status 404. `calculator(expression)` evaluates basic arithmetic without unrestricted `eval`.
- **Structured logging:** injected events include a UTC timestamp, invocation ID, tool, fault and parameters; offset events include numeric before/after summaries. Tool arguments and complete results are not logged.

## Known Limitations

- The proxy supports initialization, `tools/list` and `tools/call` over stateless Streamable HTTP, tested with protocol version 2025-11-25. It is not byte-transparent or a general-purpose MCP proxy. Pagination, notifications, resources, prompts, authentication, streaming progress, cancellation propagation and session state are not implemented.
- Each upstream operation creates a fresh session. Stateful tools are therefore outside the intended scope. Upstream protocol errors may be converted by the SDK into tool errors.
- Offset injection requires a successful calculator result with a numeric `structuredContent.result`; it is skipped otherwise. It does not corrupt arbitrary tool results.
- Concurrent scheduling can change the order of random draws. Logging is local append-only JSONL with no rotation; configured parameters may contain sensitive data.
- The demo is bound to loopback, has no authentication, and is not intended for untrusted networks. Direct dependencies are pinned, but transitive dependencies are not locked.
- The fault engine uses MCP result types but is independent of HTTP. A ContextForge adapter has not been implemented or verified.
