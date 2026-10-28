"""Versioned annotation projections, derived without importing application code.

These schemas describe complete JSON-encoded dataclass records, not constructor
defaults or the action tool's kind-dependent wire format. Canonical validators
remain necessary for bounds, identity, canonical payloads and semantic checks.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

# v2 adds Page.controls to the complete serialized record after accepted source
# composition. No v1/v2 artifacts have been generated during construction.
SCHEMA_VERSION = "2.0.0"
# Explicit public record allowlist. In particular, authority is never parsed.
RECORDS = {
    "contracts": ("PublicTask", "Target", "Intent", "Transition", "HistoryRead", "FailedAction"),
    "actions": ("Mutation", "Action"),
    "snapshot": ("Snapshot",),
    "ports": ("ActionReceipt", "InteractionReceipt"),
    "views": ("Page",),
}
ALIASES = {"contracts": ("Operation", "Origin"), "actions": ("ActionKind",)}
MAX_SOURCE_BYTES = 256 * 1024


class UnsupportedShape(ValueError):
    """No schema is emitted when a canonical annotation cannot be resolved."""


def _source(root: Path, relative: str) -> bytes:
    path = root / relative
    # Resolve only the declared source file, never discover private directories.
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise UnsupportedShape("source escapes checkout: " + relative)
    data = path.read_bytes()
    if len(data) > MAX_SOURCE_BYTES:
        raise UnsupportedShape("source exceeds cap: " + relative)
    return data


class _Projection:
    def __init__(self, root: Path):
        self.classes: dict[tuple[str, str], ast.ClassDef] = {}
        self.aliases: dict[tuple[str, str], ast.expr] = {}
        self.imports: dict[tuple[str, str], tuple[str, str]] = {}
        self.hashes: dict[str, str] = {}
        self.resolving: set[tuple[str, str]] = set()
        for module, names in RECORDS.items():
            relative = f"src/rlab/{module}.py"
            data = _source(root, relative)
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
            tree = ast.parse(data, filename=relative)
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name in names:
                    key = (module, node.name)
                    if key in self.classes:
                        raise UnsupportedShape("duplicate public class")
                    self.classes[key] = node
                elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id in ALIASES.get(module, ()):
                        key = (module, target.id)
                        if key in self.aliases:
                            raise UnsupportedShape("duplicate public alias")
                        self.aliases[key] = node.value
            # Include TYPE_CHECKING imports, but do not execute that branch.
            for node in ast.walk(tree):
                if (isinstance(node, ast.ImportFrom) and node.level == 1
                        and node.module in RECORDS):
                    for name in node.names:
                        key = (module, name.asname or name.name)
                        value = (node.module, name.name)
                        if key in self.imports and self.imports[key] != value:
                            raise UnsupportedShape("ambiguous public import")
                        self.imports[key] = value
            for name in names:
                if (module, name) not in self.classes:
                    raise UnsupportedShape(f"missing public class {module}.{name}")

    def annotation(self, module: str, node: ast.expr) -> dict[str, object]:
        if isinstance(node, ast.Constant):
            if node.value is None:
                return {"type": "null"}
            if isinstance(node.value, str):
                return self.annotation(module, ast.parse(node.value, mode="eval").body)
        if isinstance(node, ast.Name):
            primitive = {"str": "string", "int": "integer", "bool": "boolean", "float": "number"}
            if node.id in primitive:
                return {"type": primitive[node.id]}
            key = self.imports.get((module, node.id), (module, node.id))
            if key in self.classes:
                return {"$ref": "#/$defs/" + key[0] + "." + key[1]}
            if key in self.aliases:
                if key in self.resolving:
                    raise UnsupportedShape("recursive public alias")
                self.resolving.add(key)
                try:
                    return self.annotation(key[0], self.aliases[key])
                finally:
                    self.resolving.remove(key)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return {"anyOf": [self.annotation(module, node.left), self.annotation(module, node.right)]}
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            items = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            if node.value.id == "Literal":
                values = []
                for item in items:
                    if not isinstance(item, ast.Constant) or type(item.value) not in (str, int, bool):
                        raise UnsupportedShape("unsupported Literal")
                    values.append(item.value)
                return {"enum": values}
            if node.value.id == "tuple":
                if len(items) == 2 and isinstance(items[1], ast.Constant) and items[1].value is Ellipsis:
                    return {"type": "array", "items": self.annotation(module, items[0])}
                return {"type": "array", "prefixItems": [self.annotation(module, item) for item in items],
                        "minItems": len(items), "maxItems": len(items)}
        raise UnsupportedShape(f"unsupported annotation in {module}: {ast.unparse(node)}")

    def record(self, module: str, name: str) -> dict[str, object]:
        node = self.classes[module, name]
        decorated = any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass"
            or isinstance(d, ast.Name) and d.id == "dataclass" for d in node.decorator_list
        )
        if node.bases or node.keywords or not decorated:
            raise UnsupportedShape(f"unsupported dataclass declaration: {module}.{name}")
        fields: dict[str, object] = {}
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign):
                if not isinstance(statement.target, ast.Name) or statement.target.id in fields:
                    raise UnsupportedShape("unsupported or duplicate field")
                fields[statement.target.id] = self.annotation(module, statement.annotation)
        if not fields:
            raise UnsupportedShape("empty public record")
        return {"type": "object", "properties": fields, "required": list(fields),
                "additionalProperties": False,
                "$comment": f"Annotation projection of rlab.{module}.{name}; run canonical validators separately."}


def public_schema(checkout: Path) -> dict[str, object]:
    """Read only fixed public source files and return a deterministic bundle.

    No imports, plugins, type evaluation, private event logs or input receipts.
    Failure aborts the entire bundle, rather than broadening unknown types.
    """
    projection = _Projection(checkout)
    definitions = {f"{module}.{name}": projection.record(module, name)
                   for module, names in RECORDS.items() for name in names}
    own = _source(checkout, "src/rlab/public_schema.py")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:rlab:public-records:{SCHEMA_VERSION}",
        "title": "Public record annotation definitions (not a root payload validator)",
        "$comment": "Select an explicit $defs reference; root rejects every instance. Not admission or runtime evidence.",
        "not": {},
        "$defs": definitions,
        "x-schema-version": SCHEMA_VERSION,
        "x-source-sha256": projection.hashes,
        "x-generator-sha256": hashlib.sha256(own).hexdigest(),
        "x-unsupported": {"EventEnvelope": "No canonical public typed event envelope at this baseline. Trusted authority dictionaries are not actor contracts."},
    }
