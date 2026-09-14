"""Regression guard for a real bug found while redesigning the UI: hx-boost swaps
<body> only on a client-side navigation and never updates <head>, so any CSS left in a
page's own {% block extra_style %} override silently stops applying the moment a real
user reaches that page via a clicked link (nav link, "View as Impact Assessment", etc.)
instead of a typed URL or hard reload -- it only ever worked by accident, on whichever
page happened to be the first hard-loaded in the browser tab.

Fixed by moving every page's CSS into base.html's single shared stylesheet, which loads
once and never needs to change across a boosted navigation. This test keeps it that way:
if a future page defines its own extra_style content, this fails immediately instead of
shipping a page that looks right in `python scripts/demo.py` (loaded fresh) and wrong
for a real user clicking into it.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "web" / "templates"


def test_no_template_other_than_base_defines_extra_style_content():
    violations = []
    for path in TEMPLATES_DIR.glob("*.html"):
        if path.name == "base.html":
            continue
        text = path.read_text()
        match = re.search(r"\{% block extra_style %\}(.*?)\{% endblock %\}", text, re.DOTALL)
        if match and match.group(1).strip():
            violations.append(path.name)

    assert not violations, (
        "These templates define page-specific extra_style content, which hx-boost "
        "silently drops on a boosted (clicked-link) navigation -- see this file's "
        "module docstring. Move the CSS into base.html's shared stylesheet instead:\n"
        + "\n".join(violations)
    )
