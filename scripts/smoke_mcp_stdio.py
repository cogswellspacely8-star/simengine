#!/usr/bin/env python3
"""Smoke-test an MCP stdio server: initialize, list tools, call list_domains.

Usage: python3 scripts/smoke_mcp_stdio.py <server command...>
  e.g. python3 scripts/smoke_mcp_stdio.py python3 v3/mcp_server.py
       python3 scripts/smoke_mcp_stdio.py uvx simengine-mcp
Exits 0 on success, 1 on any failure. Stdlib only.

This script has no internal timeout — a hung server will hang the caller.
Callers must wrap it with the shell `timeout` command, e.g.:
  timeout 60 python3 scripts/smoke_mcp_stdio.py python3 v3/mcp_server.py
"""
import json
import subprocess
import sys

EXPECTED_TOOLS = {
    "simulate", "list_domains", "validate_config", "optimize",
    "update_bayesian", "convergence_check", "sensitivity_analysis",
    "baseline_comparison", "decide_under_uncertainty",
}


def rpc(proc, req_id, method, params=None):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout before responding")
        line = line.strip()
        if not line:
            continue
        resp = json.loads(line)
        if resp.get("id") == req_id:
            if "error" in resp:
                raise RuntimeError("RPC error from %s: %s" % (method, resp["error"]))
            return resp["result"]


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    proc = subprocess.Popen(
        argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        try:
            rpc(proc, 1, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            })
            proc.stdin.write(
                (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
            proc.stdin.flush()
            tools = {t["name"] for t in rpc(proc, 2, "tools/list")["tools"]}
            missing = EXPECTED_TOOLS - tools
            if missing:
                print("SMOKE FAIL: missing tools: %s" % sorted(missing), file=sys.stderr)
                return 1
            result = rpc(proc, 3, "tools/call", {"name": "list_domains", "arguments": {}})
            text = json.dumps(result)
            payload = json.loads(result["content"][0]["text"])
            domains = payload.get("domains", payload if isinstance(payload, list) else [])
            if not domains:
                print("SMOKE FAIL: list_domains returned no domains: %s" % text[:200],
                      file=sys.stderr)
                return 1
            print("SMOKE OK (%d tools, %d domains)" % (len(tools), len(domains)))
            return 0
        except RuntimeError as exc:
            print("SMOKE FAIL: %s" % exc, file=sys.stderr)
            return 1
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
