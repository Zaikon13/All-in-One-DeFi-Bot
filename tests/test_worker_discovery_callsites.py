"""Regression guard for the Solana-maturity force-fetch call site.

Deploy f59e7c7 crashed the discovery loop every cycle with
`Discovery error: name 'fetch_pools_by_address' is not defined`: worker.py
called the core.pair_discovery helper by its bare name, but the name is neither
imported into worker's namespace nor attribute-accessed via the `disc` alias.
The offline unit tests for Part 1 imported the function directly and so never
exercised the worker's call site. These tests parse the worker source to ensure
every core-discovery helper used inside poll_new_pools is reachable at runtime.
"""
import ast
import inspect

import worker


def _worker_src() -> str:
    return inspect.getsource(worker)


def test_force_fetch_is_qualified_with_disc_alias():
    src = _worker_src()
    assert "disc.fetch_pools_by_address(" in src, "maturity force-fetch call is missing"
    # once the qualified form is stripped, no bare call may remain
    stripped = src.replace("disc.fetch_pools_by_address(", "")
    assert "fetch_pools_by_address(" not in stripped, \
        "worker calls fetch_pools_by_address unqualified — will NameError at runtime"


def test_force_fetch_target_exists_and_is_callable():
    # the alias the worker uses must actually expose the function
    assert callable(worker.disc.fetch_pools_by_address)


def test_no_undefined_discovery_helpers_in_worker():
    """Every bare Name called in worker.py must resolve to an import, a module
    global, or a builtin — catches the whole class of 'imported in a test but
    called unqualified in the worker' bugs, not just this one function."""
    src = _worker_src()
    tree = ast.parse(src)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add((a.asname or a.name).split(".")[0])
    module_globals = set(dir(worker))
    import builtins
    builtin_names = set(dir(builtins))
    # names bound locally (defs, assignments, args, comprehensions) are fine too
    local_bound = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local_bound.add(node.name)
            for arg in getattr(node.args, "args", []) if hasattr(node, "args") else []:
                local_bound.add(arg.arg)
        elif isinstance(node, ast.arg):
            local_bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local_bound.add(node.id)

    known = imported | module_globals | builtin_names | local_bound

    # only check names in call position (the failure mode is calling an unknown fn)
    unresolved = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in known:
                unresolved.add(node.func.id)
    assert not unresolved, f"worker.py calls unresolved bare names: {sorted(unresolved)}"
