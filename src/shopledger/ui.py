"""Shared formatting and HTML components for the dashboard.

Kept separate from the page builders so a component is defined once and looks
the same on every screen.
"""

from __future__ import annotations

import html

from .icons import icon

# Nav is declared once here, so adding a screen means adding one row.
NAV: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("", [("Today", "index.html", "home")]),
    (
        "Explore",
        [
            ("Products", "products.html", "trending"),
            ("Videos", "videos.html", "play"),
            ("Creators", "creators.html", "users"),
        ],
    ),
    ("Monitor", [("Data health", "health.html", "pulse")]),
]


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def short(n: float | None) -> str:
    if n is None:
        return "---"
    n = float(n)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            return f"{n / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{n:,.0f}"


def money(n: float | None) -> str:
    return "---" if n is None else "$" + short(n)


def exact(n: float | None) -> str:
    return "---" if n is None else f"{n:,.0f}"


def nav(active: str, prefix: str = "") -> str:
    """Render the sidebar. `prefix` is '../' for pages in a subdirectory."""
    out = []
    for heading, items in NAV:
        rows = []
        if heading:
            rows.append(f"<h6>{esc(heading)}</h6>")
        for label, href, glyph in items:
            on = ' class="on"' if href == active else ""
            rows.append(f'<a href="{prefix}{href}"{on}>{icon(glyph, 20)}{esc(label)}</a>')
        out.append(f'<div class="navgroup">{"".join(rows)}</div>')
    return "".join(out)


def empty(title: str, hint: str) -> str:
    return (
        f'<div class="empty">{icon("chart-empty", 36)}<p>{esc(title)}</p><p>{esc(hint)}</p></div>'
    )


def confidence_badge(value: float | None, unattributed: int = 0) -> str:
    """Confidence is the one place the product uses semantic colour."""
    if value is None:
        return '<span class="badge flat">---</span>'
    if value >= 0.6:
        return f'<span class="badge up">{value:.2f}</span>'
    if value >= 0.3:
        return f'<span class="badge flat">{value:.2f}</span>'
    label = f"unattributed {short(unattributed)}" if unattributed else "unattributed"
    return f'<span class="badge down">{esc(label)}</span>'


def thumb(url: str | None, tall: bool = False, glyph: str = "image") -> str:
    cls = "thumb tall" if tall else "thumb"
    if url:
        return f'<img class="{cls}" src="{esc(url)}" alt="" loading="lazy">'
    return f'<span class="{cls} ph">{icon(glyph, 16)}</span>'


def product_row(index: int, row, prefix: str = "") -> str:
    """One product line for the overview's top-movers list."""
    sub = " · ".join(
        str(part) for part in (row["seller_name"], row["category_name"], row["method"]) if part
    )
    return (
        f'<div class="rowitem"><span class="rank">{index:02d}</span>'
        f"{thumb(row['image_url'])}"
        f'<span class="body">'
        f'<a class="t" href="{prefix}products/{esc(row["product_id"])}.html">'
        f"{esc(row['title'])}</a>"
        f'<span class="s">{esc(sub)}</span></span>'
        f'<span class="num"><span class="a">{money(row["revenue"])}</span>'
        f'<span class="b">{short(row["units"])} units '
        f"{confidence_badge(row['confidence'], row['unattributed'])}</span></span></div>"
    )


def video_row(index: int, row, prefix: str = "", show_product: bool = True) -> str:
    title = row["title"] or row["product_title"] or "Untitled video"
    handle = f"@{row['author_name']}" if row["author_name"] else "unknown creator"
    sub = f"{handle} · {row['product_title']}" if show_product else handle
    width = max(2.0, min(100.0, (row["share"] or 0) * 100))
    return (
        f'<div class="rowitem"><span class="rank">{index:02d}</span>'
        f"{thumb(row['cover_image_url'], tall=True, glyph='play')}"
        f'<span class="body">'
        f'<a class="t" href="{esc(row["url"])}" target="_blank" rel="noopener">{esc(title)}</a>'
        f'<span class="s">{esc(sub)}</span>'
        f'<span class="share"><i style="width:{width:.0f}%"></i></span></span>'
        f'<span class="num"><span class="a">+{short(row["view_delta"])}</span>'
        f'<span class="b">{(row["share"] or 0) * 100:.0f}% share</span></span></div>'
    )


def sortable_table(
    columns: list[tuple[str, str, bool]],
    rows: list[str],
    empty_message: str,
    table_id: str = "tbl",
) -> str:
    """A table whose headers sort client-side.

    `columns` is (label, css class, sortable). Rows carry `data-sort-N`
    attributes on each cell so sorting is numeric where it should be.
    """
    heads = []
    for index, (label, css, can_sort) in enumerate(columns):
        cls = f"{css} sortable" if can_sort else css
        attrs = f' data-col="{index}"' if can_sort else ""
        arrow = '<span class="arrow">↓</span>' if can_sort else ""
        heads.append(f'<th class="{cls}"{attrs}>{esc(label)}{arrow}</th>')

    if rows:
        body = "".join(rows)
    else:
        span = len(columns)
        body = f'<tr class="empty-row"><td colspan="{span}">{esc(empty_message)}</td></tr>'

    return (
        f'<div class="tablewrap"><table id="{table_id}">'
        f"<thead><tr>{''.join(heads)}</tr></thead><tbody>{body}</tbody></table></div>"
    )


SORT_SCRIPT = """
<script>
(function () {
  "use strict";
  document.querySelectorAll("table").forEach(function (table) {
    var tbody = table.tBodies[0];
    if (!tbody) return;
    table.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var col = Number(th.dataset.col);
        var current = th.getAttribute("aria-sort");
        var dir = current === "descending" ? "ascending" : "descending";
        table.querySelectorAll("th").forEach(function (other) {
          other.removeAttribute("aria-sort");
        });
        th.setAttribute("aria-sort", dir);

        var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) {
          return !r.classList.contains("empty-row");
        });
        rows.sort(function (a, b) {
          var av = a.cells[col] ? a.cells[col].dataset.sort : "";
          var bv = b.cells[col] ? b.cells[col].dataset.sort : "";
          var an = parseFloat(av), bn = parseFloat(bv);
          var cmp;
          if (!isNaN(an) && !isNaN(bn)) cmp = an - bn;
          else cmp = String(av).localeCompare(String(bv));
          return dir === "ascending" ? cmp : -cmp;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  var search = document.getElementById("search");
  if (search) {
    var run = function () {
      var q = search.value.trim().toLowerCase();
      document.querySelectorAll("table tbody tr").forEach(function (row) {
        if (row.classList.contains("empty-row")) return;
        row.style.display = !q || row.dataset.search.indexOf(q) !== -1 ? "" : "none";
      });
    };
    search.addEventListener("input", run);
    run();
  }
})();
</script>
"""
