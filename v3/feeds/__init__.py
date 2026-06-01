"""
SimEngine feeds — OPT-IN real-time data adapters.

Everything in this package is optional and lives outside the core engine on
purpose: these adapters are the only part of SimEngine that reaches the network.
They still use ONLY the Python standard library — importing a feed never pulls
in a third-party dependency, and the core engine never imports this package.
"""
