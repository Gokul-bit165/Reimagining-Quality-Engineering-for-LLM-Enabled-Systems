"""HTML report: complete, self-contained, accessible basics."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from qe.qareport.build import build_report
from qe.qareport.render_html import render_html
from tests.qareport.conftest import Fixture


def _html(fx: Fixture) -> tuple[str, dict]:  # type: ignore[type-arg]
    report = build_report(fx.inp)
    return render_html(report), report


def test_html_contains_every_defect_id_and_no_placeholders(fx: Fixture) -> None:
    html, report = _html(fx)
    for d in report["targets"][0]["defects"]:
        assert d["id"] in html
        for m in d["members"]:
            assert m["item_id"] in html
    text = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    assert "undefined" not in text and "NaN" not in text and ">None<" not in text
    assert "None" not in re.sub(r"<[^>]+>", " ", text).split()  # no bare Python None


def test_html_is_self_contained_without_javascript(fx: Fixture) -> None:
    html, _ = _html(fx)
    assert "<script" not in html.lower()
    assert not re.search(r"""(?:src|href)=["']https?:""", html)
    assert "@import" not in html and "url(" not in html
    assert "<svg" in html and html.count("<svg") >= 2


class _Outline(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.levels: list[int] = []
        self.tables = 0
        self.captions = 0
        self.th_without_scope = 0
        self.ids: list[str] = []
        self.lang: str | None = None
        self.svg_roles: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if tag in ("h1", "h2", "h3", "h4"):
            self.levels.append(int(tag[1]))
        if tag == "table":
            self.tables += 1
        if tag == "caption":
            self.captions += 1
        if tag == "th" and a.get("scope") is None:
            self.th_without_scope += 1
        if "id" in a and a["id"]:
            self.ids.append(a["id"])
        if tag == "svg":
            self.svg_roles.append(a.get("role"))


def test_html_accessibility_basics(fx: Fixture) -> None:
    html, _ = _html(fx)
    p = _Outline()
    p.feed(html)
    assert p.lang == "en"
    assert p.levels[0] == 1 and p.levels.count(1) == 1
    for prev, cur in zip(p.levels, p.levels[1:], strict=False):
        assert cur <= prev + 1, "heading levels must not skip"
    assert p.tables > 5 and p.captions == p.tables and p.th_without_scope == 0
    assert len(p.ids) == len(set(p.ids))
    assert all(r == "img" for r in p.svg_roles)
    assert "<title>" in html and 'name="viewport"' in html
    assert "prefers-reduced-motion" in html and "@media print" in html


def test_html_escapes_target_output(fx: Fixture) -> None:
    ev = fx.inp.targets[0]
    evil = "<img src=x onerror=alert(1)>"
    runs = {k: [{**r, "answer": evil} for r in v] for k, v in ev.runs.items()}
    report = build_report(fx.inp.model_copy(update={"targets": [ev.model_copy(
        update={"runs": runs})]}))
    html = render_html(report)
    assert evil not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
