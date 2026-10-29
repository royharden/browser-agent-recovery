"""Escaped static HTML, local relative media references only; no active scripts."""
from html import escape
from pathlib import PurePosixPath
import re

from .freeze import canonical


def media_path(value: str) -> str:
    if (not isinstance(value, str) or not value
            or re.fullmatch(r"[A-Za-z0-9_./-]+", value) is None
            or value.startswith("/") or "//" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or PurePosixPath(value).suffix.lower() not in {".png", ".jpg", ".jpeg", ".mp4", ".webm", ".txt", ".json"}):
        raise ValueError("media must be a safe relative local file, not a URL/path escape")
    return value


def render(report: dict) -> str:
    sections = []
    for table in ("tables", "contrasts"):
        sections.append("<h2>" + escape(table.title()) + "</h2><pre>"
                        + escape(canonical(report[table])) + "</pre>")
    links = []
    for row in report["rows"]:
        for value in row["media"]:
            path = media_path(value)
            links.append('<li><a href="' + escape(path, quote=True) + '">'
                         + escape(row["schedule_id"] + ": " + path) + "</a></li>")
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'img-src \'self\'; media-src \'self\'; style-src \'none\'">'
            '<title>Browser Recovery Lab report</title><body><h1>Browser Recovery Lab</h1>'
            '<p>Provisional evaluator. Runtime and independent qualification pending. '
            'Authored, scripted and mock observations are not live-model evidence.</p>'
            + "".join(sections) + "<h2>Local media</h2><ul>" + "".join(links)
            + "</ul><h2>Frozen pins</h2><pre>" + escape(canonical(report["pins"]))
            + "</pre></body></html>")
