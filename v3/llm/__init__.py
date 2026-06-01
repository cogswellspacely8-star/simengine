"""
SimEngine LLM — OPT-IN natural-language front door.

Everything in this package is optional and lives outside the core engine on
purpose: these modules are (with feeds/) the only parts of SimEngine that reach
the network. They still use ONLY the Python standard library (urllib + json) —
importing this package never pulls in a third-party dependency, and the core
engine never imports it.

It turns a plain-language question into a SimEngine config, runs it, and explains
the result. Default backend is a local model via Ollama; OpenAI-compatible and
Anthropic backends are available by environment variable.
"""
