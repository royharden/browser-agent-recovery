"""Explicit public record mapping to D1's committed 1898202 interfaces.

This is not a BrowserSession adapter. That session does not accept caller request
IDs/deadlines; the trusted backend must expose the loop's exact receipt binding.
No request identity, action response time or mutation intent is synthesized here.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import TYPE_CHECKING

from ..contracts import PublicTask
from ..providers import Action as ProviderAction, parse_action as parse_provider_action
from ..providers.port import canonical
from .loop import PublicObservation

if TYPE_CHECKING:
    from ..actions import Action, Mutation
    from ..snapshot import Snapshot


def map_action(action: ProviderAction, *, mutation: Mutation | None = None) -> Action:
    """Rename operation->kind and validate D1's stricter closed public schema.

    Click needs an ORIGINAL PUBLIC intent supplied by the trusted caller. It is
    never derived from private expected effects or guessed from a current ref.
    Unsupported lengths/control characters/wait durations are rejected, not
    silently truncated, clamped or translated to another operation.
    """
    from ..actions import Mutation, parse_action, validate_action

    source = parse_provider_action(action)
    raw = {"kind": source.operation}
    for key in ("ref", "snapshot_epoch", "value", "path", "duration_ms"):
        value = getattr(source, key)
        if value is not None:
            raw[key] = value
    mapped = parse_action(raw)
    if source.operation == "click":
        if not isinstance(mutation, Mutation):
            raise ValueError("click mapping requires original public Mutation")
        mapped = replace(mapped, intent=mutation)
    elif mutation is not None:
        raise ValueError("mutation intent is only valid for click")
    return validate_action(mapped)


def observation_from_snapshot(snapshot: Snapshot, public: PublicTask, *,
                              clock_id: str, allowed_paths: tuple[str, ...]) -> PublicObservation:
    """Serialize only a D1-validated public Snapshot; no operator handles."""
    from ..snapshot import validate_snapshot

    if not isinstance(public, PublicTask):
        raise ValueError("public task required")
    checked = validate_snapshot(snapshot, public.run_id, public.epoch)
    projection = {"url": checked.url, "body": checked.body,
                  "targets": [asdict(target) for target in checked.targets],
                  "served_version": checked.served_version}
    return PublicObservation(public.run_id, public.epoch, clock_id, public.goal,
                             checked.snapshot_epoch, canonical(projection), allowed_paths)
