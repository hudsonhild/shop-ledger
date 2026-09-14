"""Icon set.

ElevenLabs uses a bespoke stroke set rather than Lucide or Hugeicons. Measured
from their live bundles on 14 September 2026, the contract is:

    viewBox="0 0 18 18"   fill="none"   stroke="currentColor"
    stroke-width="1.5"    stroke-linecap="round"   stroke-linejoin="round"

`ARROW_LEFT` below is lifted verbatim from an ElevenLabs bundle and is the
reference the rest of the set is drawn against. Their full app set is loaded
behind authentication, so the remaining marks here are drawn to that same grid
and stroke treatment rather than extracted.

Icons render at the secondary text tone and only darken on an active row, which
is how ElevenLabs colours them. A full-black icon row is the tell that someone
guessed.
"""

from __future__ import annotations

# Verbatim from an ElevenLabs bundle. Do not redraw.
ARROW_LEFT = "M7.5 4.5 3 9l4.5 4.5M3.75 9H15"

_PATHS: dict[str, str] = {
    "arrow-left": ARROW_LEFT,
    # Sidebar
    "home": "M2.75 7.75 9 2.75l6.25 5V14a1.25 1.25 0 0 1-1.25 1.25H4A1.25 1.25 0 0 1 2.75 14z",
    "trending": "M2.75 12.5 7 8.25l2.5 2.5 5.75-5.75M15.25 5v3.5M15.25 5h-3.5",
    "play": "M6.75 4.4a.5.5 0 0 1 .76-.43l6.1 3.6a.5.5 0 0 1 0 .86l-6.1 3.6a.5.5 0 0 1-.76-.43z",
    "users": "M11.5 15.25v-1.5a2.75 2.75 0 0 0-2.75-2.75h-3A2.75 2.75 0 0 0 3 13.75v1.5M7.25 8.25a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5M15.25 15.25v-1.5a2.75 2.75 0 0 0-2-2.65",
    "pulse": "M2.75 9h2.5l1.75-4 2.5 8 1.75-4h4",
    # Controls
    "chevron-down": "M5 7.25 9 11.25l4-4",
    "filter": "M3 4.75h12M5.5 9h7M7.75 13.25h2.5",
    "external": "M7.25 10.75 14 4M14 4h-3.75M14 4v3.75M14 10.25v3a.75.75 0 0 1-.75.75h-8.5A.75.75 0 0 1 4 13.25v-8.5A.75.75 0 0 1 4.75 4h3",
    "calendar": "M3.25 6.5h11.5M5.75 2.75v2M12.25 2.75v2M4.5 4.25h9a1.25 1.25 0 0 1 1.25 1.25v8A1.25 1.25 0 0 1 13.5 14.75h-9A1.25 1.25 0 0 1 3.25 13.5v-8A1.25 1.25 0 0 1 4.5 4.25",
    "layers": "M9 2.75 2.75 6 9 9.25 15.25 6zM2.75 12 9 15.25 15.25 12M2.75 9 9 12.25 15.25 9",
    # States
    "image": "M3.25 4.75h11.5v8.5H3.25zM3.25 11l3-3 2.25 2.25L11.5 7.5l3.25 3.25M6.25 7.25h.008",
    "chart-empty": "M3 15V8.5M7.5 15V4.5M12 15v-5M15.75 15H2.25",
}


def icon(name: str, size: int = 15, extra_class: str = "") -> str:
    """Return one inline SVG. Unknown names fall back to a neutral dot."""
    path = _PATHS.get(name)
    if path is None:  # pragma: no cover - guards typos in templates
        path = "M9 9h.01"
    classes = f' class="{extra_class}"' if extra_class else ""
    return (
        f'<svg{classes} width="{size}" height="{size}" viewBox="0 0 18 18" fill="none" '
        f'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true"><path d="{path}"/></svg>'
    )


def wordmark(size: int = 16) -> str:
    """The Shop Ledger mark: three bars, a ledger read as a chart.

    This is the venture's own identity asset, which is the one category the
    ElevenLabs system does not supply, so it is filled rather than stroked.
    """
    return (
        f'<svg class="glyph" width="{size}" height="{size}" viewBox="0 0 18 18" '
        f'fill="currentColor" aria-hidden="true">'
        f'<rect x="2" y="7.5" width="3.2" height="8.5" rx="1.1"/>'
        f'<rect x="7.4" y="2.5" width="3.2" height="13.5" rx="1.1"/>'
        f'<rect x="12.8" y="10.5" width="3.2" height="5.5" rx="1.1"/></svg>'
    )
