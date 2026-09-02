"""Brand-palette SVG infographic templates. No diffusion models."""
from __future__ import annotations

from typing import Any


PALETTE = {
    "bg": "#0b1220",
    "card": "#151c2c",
    "line": "#334155",
    "text": "#e8eef7",
    "muted": "#94a3b8",
    "accent": "#7c6bb5",
    "blue": "#3b6ea8",
    "slate": "#1e293b",
}


def _esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_infographic_svg(data: dict[str, Any]) -> str:
    facts = (data.get("facts") or [])[:6]
    comparison = data.get("comparison")
    timeline = data.get("timeline") or []
    if comparison:
        return _comparison(data, facts, comparison)
    if timeline:
        return _timeline(data, facts, timeline)
    return _facts(data, facts)


def _header(data: dict[str, Any]) -> str:
    return f"""
  <text x="64" y="72" fill="{PALETTE['accent']}" font-size="18" letter-spacing="4" font-family="Inter, DejaVu Sans, sans-serif">ATLASLM</text>
  <text x="64" y="130" fill="{PALETTE['text']}" font-size="42" font-weight="700" font-family="Inter, DejaVu Sans, sans-serif">{_esc(data.get("headline") or "Key findings")}</text>
  <text x="64" y="172" fill="{PALETTE['muted']}" font-size="20" font-family="Inter, DejaVu Sans, sans-serif">{_esc(data.get("kicker") or "Grounded in your notebook sources")}</text>
"""


def _facts(data: dict[str, Any], facts: list[dict[str, Any]]) -> str:
    cards = []
    for idx, fact in enumerate(facts):
        col = idx % 2
        row = idx // 2
        x = 64 + col * 536
        y = 220 + row * 280
        cards.append(f"""
  <rect x="{x}" y="{y}" width="504" height="248" rx="24" fill="{PALETTE['card']}" stroke="{PALETTE['line']}"/>
  <text x="{x + 32}" y="{y + 70}" fill="{PALETTE['muted']}" font-size="18" font-family="Inter, DejaVu Sans, sans-serif">{_esc(fact.get("label"))}</text>
  <text x="{x + 32}" y="{y + 140}" fill="{PALETTE['text']}" font-size="40" font-weight="700" font-family="Inter, DejaVu Sans, sans-serif">{_esc(fact.get("value"))}</text>
  <text x="{x + 32}" y="{y + 188}" fill="{PALETTE['accent']}" font-size="16" font-family="Inter, DejaVu Sans, sans-serif">{_esc(fact.get("cite") or "")}</text>
""")
    return _wrap("".join([_header(data), *cards]))


def _comparison(data: dict[str, Any], facts: list[dict[str, Any]], comparison: dict[str, Any]) -> str:
    body = f"""
  <rect x="64" y="220" width="504" height="320" rx="24" fill="{PALETTE['card']}" stroke="{PALETTE['line']}"/>
  <rect x="632" y="220" width="504" height="320" rx="24" fill="{PALETTE['card']}" stroke="{PALETTE['accent']}"/>
  <text x="96" y="280" fill="{PALETTE['muted']}" font-size="20">{_esc(comparison.get("left"))}</text>
  <text x="96" y="380" fill="{PALETTE['text']}" font-size="44" font-weight="700">{_esc(comparison.get("left_value"))}</text>
  <text x="664" y="280" fill="{PALETTE['muted']}" font-size="20">{_esc(comparison.get("right"))}</text>
  <text x="664" y="380" fill="{PALETTE['text']}" font-size="44" font-weight="700">{_esc(comparison.get("right_value"))}</text>
"""
    extras = []
    for idx, fact in enumerate(facts[:4]):
        y = 580 + idx * 180
        extras.append(f"""
  <rect x="64" y="{y}" width="1072" height="160" rx="20" fill="{PALETTE['slate']}"/>
  <text x="96" y="{y + 60}" fill="{PALETTE['muted']}" font-size="18">{_esc(fact.get("label"))}</text>
  <text x="96" y="{y + 112}" fill="{PALETTE['text']}" font-size="28" font-weight="700">{_esc(fact.get("value"))}</text>
""")
    return _wrap(_header(data) + body + "".join(extras))


def _timeline(data: dict[str, Any], facts: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> str:
    items = []
    y = 240
    for idx, event in enumerate(timeline[:6]):
        items.append(f"""
  <circle cx="96" cy="{y}" r="12" fill="{PALETTE['accent']}"/>
  <text x="140" y="{y - 6}" fill="{PALETTE['accent']}" font-size="18">{_esc(event.get("when"))}</text>
  <text x="140" y="{y + 28}" fill="{PALETTE['text']}" font-size="24">{_esc(event.get("what"))}</text>
""")
        if idx < len(timeline[:6]) - 1:
            items.append(f'<line x1="96" y1="{y + 14}" x2="96" y2="{y + 110}" stroke="{PALETTE["line"]}" stroke-width="3"/>')
        y += 130
    extras = []
    for idx, fact in enumerate(facts[:3]):
        extras.append(f"""
  <rect x="64" y="{y + 40 + idx * 150}" width="1072" height="130" rx="18" fill="{PALETTE['card']}"/>
  <text x="96" y="{y + 90 + idx * 150}" fill="{PALETTE['muted']}" font-size="16">{_esc(fact.get("label"))}</text>
  <text x="96" y="{y + 132 + idx * 150}" fill="{PALETTE['text']}" font-size="26" font-weight="700">{_esc(fact.get("value"))}</text>
""")
    return _wrap(_header(data) + "".join(items) + "".join(extras))


def _wrap(inner: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1500" viewBox="0 0 1200 1500">
  <rect width="1200" height="1500" fill="{PALETTE['bg']}"/>
  {inner}
  <text x="64" y="1456" fill="{PALETTE['muted']}" font-size="16" font-family="Inter, DejaVu Sans, sans-serif">Values taken only from indexed AtlasLM sources</text>
</svg>
"""
