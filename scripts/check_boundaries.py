"""Read-only AST/TOML guidance; never imports the application or proves isolation.

Run with Python 3.12+: python scripts/check_boundaries.py [--root CHECKOUT].
Exit 0: declared static scope resolved with no findings; 1: violations;
2: unresolved/incomplete scope (possibly also violations). No files are written.
"""
from __future__ import annotations

import argparse
import ast
from collections import deque
import fnmatch
import json
import os
from pathlib import Path
import sys
import tomllib


# These are the only current public roots, plus explicitly named future layers.
PUBLIC_MODULES = frozenset({
    "rlab.contracts", "rlab.actions", "rlab.snapshot", "rlab.recovery",
    "rlab.routing", "rlab.scripted", "rlab.public_schema",
})
PUBLIC_LAYERS = ("rlab.agents", "rlab.providers", "rlab.worker", "rlab.recovery")
# Trusted modules are exempt only as ENTRY ROOTS, never as dependency targets of
# a public root. New modules need a declared layer, not a broad trusted wildcard.
TRUSTED_ROOTS = {
    "rlab": "inert package namespace; still traversed for public imports",
    "rlab.cli": "operator CLI",
    "rlab.authority": "private state and sealed evidence",
    "rlab.driver": "trusted development authority adapter",
    "rlab.host": "trusted task host",
    "rlab.executor": "trusted action controller",
    "rlab.browser": "trusted browser facade",
    "rlab.ports": "trusted controller ports and public receipt record",
    "rlab.views": "trusted renderer; ordinary page projection",
    "rlab.faults": "private fault schedule",
    "rlab.lag": "trusted visibility schedule",
    "rlab.admission": "operator admission interface",
    "rlab.admission.schemas": "operator admission schema",
    "rlab.admission.validator": "operator admission validator",
}
FORBIDDEN_MODULES = frozenset({
    "rlab.cli", "rlab.authority", "rlab.driver", "rlab.host", "rlab.executor",
    "rlab.browser", "rlab.ports", "rlab.faults", "rlab.lag", "rlab.admission",
})
FORBIDDEN_PARTS = frozenset({
    "authority", "evaluation", "heldout", "held_out", "admin", "admin_socket",
    "database", "db", "sqlite", "sqlite3", "sqlalchemy", "psycopg", "psycopg2",
    "secrets", "secret", "credentials", "credential", "keyring", "dotenv",
    "config", "configparser", "settings", "private_spec", "taskspec", "oracle",
})
# Never open excluded trees or files, even when an import points at one.
EXCLUDED = frozenset({
    "attic", "reviews", "exports", "evaluation", "heldout", "held_out",
    "auth", "credentials", "secrets", "tokens", "__pycache__",
})


def prefix(name: str, base: str) -> bool:
    return name == base or name.startswith(base + ".")


def public(name: str) -> bool:
    return name in PUBLIC_MODULES or any(prefix(name, layer) for layer in PUBLIC_LAYERS)


def forbidden(name: str) -> bool:
    return (any(prefix(name, base) for base in FORBIDDEN_MODULES)
            or bool(set(name.lower().split(".")) & FORBIDDEN_PARTS))


def excluded_name(name: str) -> bool:
    lower = name.lower()
    return (name.startswith(".") or lower in EXCLUDED
            or (any(part in lower for part in ("secret", "credential", "token", "auth"))
                and lower != "authority.py"))


def declared_symbols(tree: ast.Module) -> set[str]:
    """Names declared at module scope, including conditional declarations."""
    result: set[str] = set()
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            result.add(node.name)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result.update(item.asname or item.name.split(".")[0] for item in node.names)
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            result.add(node.id)
        pending.extend(ast.iter_child_nodes(node))
    return result


def run(root: Path) -> dict[str, object]:
    violations: set[str] = set()
    unresolved: set[str] = set()
    modules: dict[str, tuple[Path, ast.Module]] = {}
    root = root.absolute()
    source = root / "src" / "rlab"
    # No application import, file execution, plugin loading, or arbitrary glob.
    for path in (root, root / "src", source, root / "pyproject.toml"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            unresolved.add(f"refused linked scope: {path.name}")
    scope_safe = not unresolved
    if scope_safe and source.is_dir():
        for directory, dirs, files in os.walk(source, followlinks=False):
            base = Path(directory)
            kept = []
            for item in sorted(dirs):
                child = base / item
                if excluded_name(item):
                    continue
                if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                    unresolved.add(f"refused linked source directory: {child.relative_to(root)}")
                else:
                    kept.append(item)
            dirs[:] = kept
            for item in sorted(files):
                if not item.endswith(".py") or excluded_name(item):
                    continue
                path = base / item
                if path.is_symlink():
                    unresolved.add(f"refused linked source: {path.relative_to(root)}")
                    continue
                relative = path.relative_to(root / "src").with_suffix("")
                parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
                name = ".".join(parts)
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                except (OSError, UnicodeError, SyntaxError) as error:
                    unresolved.add(f"{name}: source parse unavailable ({type(error).__name__})")
                    continue
                if name in modules:
                    unresolved.add(f"{name}: module/package name collision")
                modules[name] = (path, tree)
    roots = sorted(name for name in modules if public(name))
    if not modules or not roots:
        unresolved.add("no-input: no parsed modules or no declared public roots")
    for name in modules:
        if not public(name) and name not in TRUSTED_ROOTS:
            unresolved.add(f"{name}: undeclared layer; assign explicitly before claiming complete scope")

    edges: dict[str, set[str]] = {name: set() for name in modules}
    findings: dict[str, set[str]] = {name: set() for name in modules}
    unknowns: dict[str, set[str]] = {name: set() for name in modules}
    symbols = {name: declared_symbols(tree) for name, (_, tree) in modules.items()}

    def dependency(owner: str, target: str, line: int) -> None:
        label = f"{owner}:{line} -> {target}"
        if forbidden(target):
            findings[owner].add(label)
        if target in modules:
            edges[owner].add(target)
            parts = target.split(".")
            for index in range(1, len(parts)):
                package = ".".join(parts[:index])
                if package in modules:
                    edges[owner].add(package)
        elif target.split(".")[0] == "rlab":
            unknowns[owner].add(label + " (unresolved local module)")
        elif target.split(".")[0] not in sys.stdlib_module_names and target != "__future__":
            unknowns[owner].add(label + " (external dependency closure not inspected)")

    def qualified(node: ast.AST, aliases: dict[str, str]) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = qualified(node.value, aliases)
            return parent + "." + node.attr if parent else ""
        return ""

    for name, (path, tree) in modules.items():
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        aliases: dict[str, str] = {}
        # ast.walk includes conditional, function-local and TYPE_CHECKING imports.
        # This is deliberately conservative source dependence, not runtime reachability.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
                    dependency(name, item.name, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                parts = package.split(".")
                if node.level > len(parts):
                    unknowns[name].add(f"{name}:{node.lineno}: relative import escapes package")
                    continue
                base = ".".join(parts[:len(parts) - node.level + 1]) if node.level else ""
                target = ".".join(part for part in (base, node.module or "") if part)
                dependency(name, target, node.lineno)
                for item in node.names:
                    aliases[item.asname or item.name] = target + "." + item.name
                    if item.name == "*":
                        unknowns[name].add(f"{name}:{node.lineno}: wildcard import not resolved")
                    elif target + "." + item.name in modules:
                        dependency(name, target + "." + item.name, node.lineno)
                    elif forbidden(target + "." + item.name):
                        findings[name].add(f"{name}:{node.lineno} -> {target}.{item.name}")
                    elif target in modules and item.name not in symbols[target]:
                        unknowns[name].add(f"{name}:{node.lineno} -> {target}.{item.name} (unresolved local symbol)")
        # Track straightforward loader alias assignments. Rebinding/indirect
        # reflection cannot be proved by AST and remains an explicit limitation.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = qualified(node.value, aliases)
                if value:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            aliases[target.id] = value
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = qualified(node.func, aliases)
            if (call in {"__import__", "builtins.__import__", "eval", "exec", "compile",
                         "builtins.eval", "builtins.exec", "builtins.compile"}
                    or call.startswith("importlib.") or call.startswith("runpy.")):
                unknowns[name].add(f"{name}:{node.lineno}: dynamic import/code loader {call}; closure unresolved")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {"load_module", "exec_module", "find_spec"}:
                unknowns[name].add(f"{name}:{node.lineno}: possible dynamic loader method {node.func.attr}; closure unresolved")
            if call in {"os.getenv", "os.environ.get", "os.environ.__getitem__"}:
                findings[name].add(f"{name}:{node.lineno}: environment/config entrypoint {call}")
        for node in ast.walk(tree):
            if qualified(node, aliases) == "os.environ":
                findings[name].add(f"{name}:{getattr(node, 'lineno', 0)}: environment/config entrypoint os.environ")
            if qualified(node, aliases) in {"sys.path", "sys.meta_path", "sys.path_hooks", "__path__"}:
                unknowns[name].add(f"{name}:{getattr(node, 'lineno', 0)}: import search path access; closure unresolved")

    reached: set[str] = set()
    for origin in roots:
        queue = deque([(origin, (origin,))])
        seen: set[str] = set()
        while queue:
            name, chain = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            reached.add(name)
            route = " -> ".join(chain)
            violations.update(route + ": " + finding for finding in findings[name])
            unresolved.update(route + ": " + finding for finding in unknowns[name])
            for target in sorted(edges[name]):
                if target not in seen:
                    queue.append((target, chain + (target,)))

    # Interpret only a narrow setuptools source-discovery configuration. Other
    # backends/custom discovery are unresolved; never assume exclusion by default.
    try:
        if not scope_safe:
            raise ValueError("linked scope refused")
        with (root / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        build = project.get("build-system", {})
        setup = project.get("tool", {}).get("setuptools", {})
        find = setup.get("packages", {}).get("find", {}) if isinstance(setup.get("packages", {}), dict) else {}
        if build.get("build-backend") != "setuptools.build_meta" or build.get("backend-path"):
            unresolved.add("packaging: unsupported/custom backend")
        if (find.get("where") != ["src"] or find.get("include") != ["rlab*"]
                or any(key not in {"where", "include", "exclude", "namespaces"} for key in find)
                or any(key not in {"packages", "include-package-data", "package-data", "exclude-package-data"} for key in setup)):
            unresolved.add("packaging: discovery differs from bounded src/rlab include policy")
        patterns = find.get("include", [])
        excluded = find.get("exclude", [])
        if not isinstance(patterns, list) or not isinstance(excluded, list) or not all(isinstance(v, str) for v in patterns + excluded):
            unresolved.add("packaging: invalid include/exclude patterns")
        else:
            for family in ("evaluation", "heldout", "held_out"):
                for candidate in (family, family + ".private", "rlab." + family, "rlab." + family + ".private"):
                    if (any(fnmatch.fnmatchcase(candidate, pattern) for pattern in patterns)
                            and not any(fnmatch.fnmatchcase(candidate, pattern) for pattern in excluded)):
                        violations.add(f"packaging: discovery would include forbidden package {candidate}")
        if setup.get("package-data") or setup.get("include-package-data", True):
            unresolved.add("packaging: package-data/default include-package-data requires later artifact inspection")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        unresolved.add(f"packaging: TOML/discovery unavailable ({type(error).__name__})")
    return {
        "scope": "src/rlab/**/*.py and pyproject.toml only; no application imports",
        "scanned_modules": len(modules), "public_roots": roots,
        "public_transitive_modules": len(reached),
        "trusted_entrypoint_exemptions": TRUSTED_ROOTS,
        "violations": sorted(violations), "unresolved": sorted(unresolved),
        "status": "incomplete" if unresolved else "violations" if violations else "static_scope_clear",
        "limitations": [
            "AST imports include TYPE_CHECKING, conditional and function-local dependencies conservatively.",
            "Reflection, arbitrary loader aliases, monkeypatching and runtime sys.path changes are not proven.",
            "No installed-wheel contents, worker UID/ACL/egress, custody, admission or runtime security qualification.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).absolute().parents[1])
    args = parser.parse_args()
    result = run(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["unresolved"] else 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
