"""Original development HTML; transport/fault injection remains a separate seam."""
from dataclasses import dataclass
from html import escape
from uuid import uuid4

from .contracts import PublicTask, Target


@dataclass(frozen=True)
class Page:
    snapshot_epoch: str
    html: str
    targets: tuple[Target, ...]
    controls: tuple[Target, ...] = ()


def render(task: PublicTask, family: str, items: tuple[str, ...]) -> Page:
    """Server supplies visible items; no expected-effect table enters this page.

    refs intentionally change on every render. Executor must preserve captured
    refs for R0/R1; only R3/R23 opt in to semantic re-resolution.
    """
    if family not in {"F1", "F2", "F3"}:
        raise ValueError("development family only")
    epoch = uuid4().hex
    targets = []
    controls = []
    rows = []
    labels = {"F1": "Order", "F2": "Create ticket", "F3": "Delete"}
    choices = ("general", "billing") if family == "F2" else items
    for index, item in enumerate(choices):
        ref = f"{epoch}-{index}"
        target = Target(ref, epoch, "button", labels[family], item)
        targets.append(target)
        control_ref = f"{epoch}-body-{index}"
        if family == "F2":
            controls.append(Target(control_ref, epoch, "textbox", "Body", item))
        field = (f'<label>Body <textarea id="{control_ref}" name="body" required></textarea></label>'
                 if family == "F2" else
                 '<label>Quantity <input name="quantity" value="1" readonly></label>'
                 if family == "F1" else "")
        rows.append(f'<section aria-label="{escape(item, quote=True)}">'
                    f'<p>{escape(item)}</p><form method="post" action="{task.start_path}/action">'
                    f'<input type="hidden" name="snapshot" value="{epoch}">'
                    f'<input type="hidden" name="ref" value="{ref}">'
                    f'{field}<button id="{ref}">{labels[family]}</button>'
                    '</form></section>')
    markup = ('<!doctype html><html lang="en"><meta charset="utf-8">'
              '<title>Browser Recovery Lab — development task</title><body>'
              f'<h1>{escape(task.goal)}</h1>{"".join(rows)}'
              f'<a href="{task.start_path}/history">Transition history</a></body></html>')
    # Keep mutation refs separate: DevelopmentTask/remap_page operate only on
    # button targets. Public input controls never become submission targets.
    return Page(epoch, markup, tuple(targets), tuple(controls))
