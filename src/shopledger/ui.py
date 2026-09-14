"""Shared formatting and Polaris components for the dashboard.

Every component here is a Polaris component copied from @shopify/polaris 13.9.5
and the live admin, named after its Polaris counterpart so the CSS in base.html
and the markup here can be traced back to the same source. A component is
defined once and looks the same on every screen.
"""

from __future__ import annotations

import html
import json
import math

from .icons import icon

# Nav is declared once here, so adding a screen means adding one row.
# (section heading or "", [(label, href, glyph)])
NAV: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "",
        [
            ("Today", "index.html", "home"),
            ("Products", "products.html", "product"),
            ("Videos", "videos.html", "play"),
            ("Creators", "creators.html", "person"),
        ],
    ),
    ("Monitor", [("Data health", "health.html", "pulse")]),
]

PAGE_SIZE = 50


# ------------------------------------------------------------------ formatting


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


def missing() -> str:
    """A reading that does not exist yet is a static grey skeleton, never a dash."""
    return '<span class="Polaris-SkeletonBodyText Polaris-SkeletonBodyText--inline"></span>'


# -------------------------------------------------------------------- frame


def nav(active: str, prefix: str = "") -> str:
    """Polaris Navigation: sections of 28px rows with a 20px icon slot."""
    out = []
    for heading, items in NAV:
        rows = []
        if heading:
            rows.append(
                '<div class="Polaris-Navigation__SectionHeading"><button type="button">'
                f"{esc(heading)}"
                '<svg viewBox="0 0 5 16" fill="currentColor" aria-hidden="true">'
                '<path d="M1.06 4.53a.75.75 0 0 1 1.06-1.06l3.75 3.75a.75.75 0 0 1 0 1.06l-3.75 3.75a.75.75 0 1 1-1.06-1.06L4.27 8 1.06 4.53Z"/>'
                "</svg></button></div>"
            )
        for label, href, glyph in items:
            on = " Polaris-Navigation__ItemInnerWrapper--selected" if href == active else ""
            current = ' aria-current="page"' if href == active else ""
            rows.append(
                '<li class="Polaris-Navigation__ListItem">'
                f'<div class="Polaris-Navigation__ItemInnerWrapper{on}">'
                f'<a class="Polaris-Navigation__Item" href="{prefix}{href}"{current}>'
                f'<span class="Polaris-Navigation__Icon">{icon(glyph, 16)}</span>'
                f'<span class="Polaris-Navigation__Text">{esc(label)}</span></a></div></li>'
            )
        out.append(f'<ul class="Polaris-Navigation__Section">{"".join(rows)}</ul>')
    return "".join(out)


def run_status(last) -> str:
    """The top bar status chip: a dot and the last run, like the admin's store chip."""
    if last is None:
        return (
            '<span class="TopBar__Status warn" data-tooltip="No run has finished yet">'
            '<i class="dot"></i>No run recorded</span>'
        )
    clean = (last["errors"] or 0) == 0
    state = "clean" if clean else f"{last['errors']} errors"
    klass = "TopBar__Status" if clean else "TopBar__Status warn"
    stamp = last["finished_at"][11:16] + " UTC"
    return (
        f'<span class="{klass}" data-tooltip="Stage {esc(last["stage"])}, '
        f'{esc(last["calls"] or 0)} calls"><i class="dot"></i>'
        f"Last run {esc(stamp)} · {esc(state)}</span>"
    )


# ----------------------------------------------------------------- primitives


def button(
    label: str,
    *,
    href: str | None = None,
    variant: str = "secondary",
    icon_name: str | None = None,
    icon_only: bool = False,
    size: str = "medium",
    disabled: bool = False,
    attrs: str = "",
    external: bool = False,
) -> str:
    """Polaris Button. variant: primary | secondary | tertiary | plain."""
    classes = ["Polaris-Button", f"Polaris-Button--variant{variant.capitalize()}"]
    if icon_only:
        classes.append("Polaris-Button--iconOnly")
    if size != "medium":
        classes.append(f"Polaris-Button--size{size.capitalize()}")
    if disabled:
        classes.append("Polaris-Button--disabled")
    glyph = icon(icon_name, 16) if icon_name else ""
    inner = glyph if icon_only else f"{glyph}<span>{esc(label)}</span>"
    aria = f' aria-label="{esc(label)}"' if icon_only else ""
    cls = " ".join(classes)
    if href:
        target = ' target="_blank" rel="noopener"' if external else ""
        return f'<a class="{cls}" href="{esc(href)}"{target}{aria}{attrs}>{inner}</a>'
    dis = " disabled" if disabled else ""
    return f'<button class="{cls}" type="button"{aria}{dis}{attrs}>{inner}</button>'


def badge(label: str, tone: str = "", pip: str | None = None, tooltip: str | None = None) -> str:
    """Polaris Badge. tone: success | info | attention | warning | critical | new.

    `pip` draws the progress dot: incomplete | partiallyComplete | complete.
    """
    cls = "Polaris-Badge" + (f" Polaris-Badge--tone{tone.capitalize()}" if tone else "")
    dot = f'<span class="Polaris-Badge__Pip Polaris-Badge__Pip--{pip}"></span>' if pip else ""
    tip = f' data-tooltip="{esc(tooltip)}" tabindex="0"' if tooltip else ""
    return f'<span class="{cls}"{tip}>{dot}{esc(label)}</span>'


def confidence_badge(value: float | None, unattributed: int = 0) -> str:
    """Confidence is where the product uses semantic colour and the progress pip."""
    if value is None:
        return badge("No reading", pip="incomplete")
    if value >= 0.6:
        return badge(f"{value:.2f}", "success", pip="complete", tooltip="Sold and stock deltas agree")
    if value >= 0.3:
        return badge(
            f"{value:.2f}", "attention", pip="partiallyComplete", tooltip="Deltas partly disagree"
        )
    label = f"unattributed {short(unattributed)}" if unattributed else "unattributed"
    return badge(label, "critical", pip="incomplete", tooltip="No video could be assigned the sale")


def thumb(url: str | None, tall: bool = False, glyph: str = "image") -> str:
    cls = "Polaris-Thumbnail Polaris-Thumbnail--tall" if tall else "Polaris-Thumbnail"
    if url:
        return f'<span class="{cls}"><img src="{esc(url)}" alt="" loading="lazy"></span>'
    return f'<span class="{cls} ph">{icon(glyph, 16)}</span>'


def avatar(name: str, url: str | None = None) -> str:
    """Polaris Avatar: seven fills chosen by the name, initials on top."""
    style = (sum(ord(c) for c in name) % 7) + 1
    initials = "".join(part[0] for part in name.replace("_", " ").split()[:2]) or name[:2]
    if url:
        return f'<span class="Polaris-Avatar Polaris-Avatar--style{style}"><img src="{esc(url)}" alt=""></span>'
    return f'<span class="Polaris-Avatar Polaris-Avatar--style{style}">{esc(initials[:2])}</span>'


def progress(fraction: float, tone: str = "highlight") -> str:
    pct = max(0.0, min(1.0, fraction or 0.0))
    return (
        f'<span class="Polaris-ProgressBar Polaris-ProgressBar--sizeSmall Polaris-ProgressBar--tone{tone.capitalize()}" '
        f'role="progressbar" aria-valuenow="{pct * 100:.0f}" aria-valuemin="0" aria-valuemax="100">'
        f'<span class="Polaris-ProgressBar__Indicator" style="--pc-progress-bar-percent:{pct:.3f}"></span></span>'
    )


def text_field(field_id: str, placeholder: str, value: str = "", prefix_icon: str | None = "search") -> str:
    prefix = f'<span class="Polaris-TextField__Prefix">{icon(prefix_icon, 20)}</span>' if prefix_icon else ""
    has = " Polaris-TextField--hasValue" if value else ""
    return (
        f'<div class="Polaris-TextField{has}">{prefix}'
        f'<input class="Polaris-TextField__Input" id="{esc(field_id)}" type="search" '
        f'placeholder="{esc(placeholder)}" value="{esc(value)}" autocomplete="off">'
        f'<button class="Polaris-TextField__ClearButton" type="button" aria-label="Clear">{icon("x-circle", 16)}</button>'
        '<div class="Polaris-TextField__Backdrop"></div></div>'
    )


def kv(pairs: list[tuple[str, str]]) -> str:
    """Polaris DescriptionList."""
    rows = "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs)
    return f'<dl class="Polaris-DescriptionList">{rows}</dl>'


# ---------------------------------------------------------------------- cards


def card(
    body: str,
    *,
    title: str | None = None,
    meta: str | None = None,
    actions: str = "",
    flush: bool = False,
    footer: str | None = None,
    extra_class: str = "",
) -> str:
    """Polaris Card: bevelled, radius 12, padding 16, heading-sm title."""
    head = ""
    if title:
        meta_html = f'<span class="Polaris-Text--subdued t-subdued">{esc(meta)}</span>' if meta else ""
        head = (
            f'<div class="Polaris-Card__Header"><h2 class="t-heading-sm">{esc(title)}</h2>'
            f'<span class="spacer"></span>{meta_html}{actions}</div>'
        )
    section_cls = "Polaris-Card__Section Polaris-Card__Section--flush" if flush else "Polaris-Card__Section"
    foot = f'<div class="Polaris-Card__Footer">{footer}</div>' if footer else ""
    cls = f"Polaris-Card {extra_class}".strip()
    return f'<section class="{cls}">{head}<div class="{section_cls}">{body}</div>{foot}</section>'


def banner(title: str, content: str, tone: str = "info", within_card: bool = False) -> str:
    glyphs = {"info": "info", "success": "check-circle", "warning": "alert-triangle", "critical": "alert-diamond"}
    cls = f"Polaris-Banner Polaris-Banner--tone{tone.capitalize()}"
    if within_card:
        cls += " Polaris-Banner--withinCard"
    return (
        f'<div class="{cls}" role="status"><span class="Polaris-Banner__Icon">{icon(glyphs.get(tone, "info"), 20)}</span>'
        f'<div class="Polaris-Banner__Body"><p class="Polaris-Banner__Title">{esc(title)}</p>'
        f'<p class="Polaris-Banner__Content">{content}</p></div></div>'
    )


def empty(title: str, hint: str, action: str = "", glyph: str = "chart-empty") -> str:
    """Polaris EmptyState: heading-md, body-sm, one action, fades in over 150ms."""
    act = f'<div class="Polaris-EmptyState__Actions">{action}</div>' if action else ""
    return (
        f'<div class="Polaris-EmptyState"><span class="Polaris-EmptyState__Image">{icon(glyph, 44)}</span>'
        f"<h3>{esc(title)}</h3><p>{esc(hint)}</p>{act}</div>"
    )


def footer_help(text: str) -> str:
    return f'<div class="Polaris-FooterHelp">{icon("info", 20)}<span>{text}</span></div>'


def metric_card(
    label: str,
    value: str,
    *,
    delta: float | None = None,
    delta_label: str = "vs previous day",
    series: list[float] | None = None,
    tooltip: str | None = None,
    unit: str = "",
) -> str:
    """The Analytics metric card: heading-sm, big number, delta and a sparkline."""
    tip = f' data-tooltip="{esc(tooltip)}" tabindex="0"' if tooltip else ""
    delta_html = ""
    if delta is not None and not math.isnan(delta):
        direction = "up" if delta > 0 else "down" if delta < 0 else ""
        arrow = icon("arrow-up" if delta > 0 else "arrow-down", 12) if delta else ""
        delta_html = (
            f'<span class="Metric__Delta {direction}" data-tooltip="{esc(delta_label)}">'
            f"{arrow}{abs(delta) * 100:.0f}%</span>"
        )
    spark = ""
    if series and len(series) >= 2:
        spark = f'<div class="Metric__Spark">{sparkline(series)}</div>'
    small = f"<small>{esc(unit)}</small>" if unit else ""
    return (
        f'<section class="Polaris-Card"><div class="Metric">'
        f'<div class="Metric__Head"{tip}>{esc(label)}</div>'
        f'<div class="Metric__Value"><span>{value}{small}</span>{delta_html}</div>{spark}</div></section>'
    )


def sparkline(values: list[float], width: int = 200, height: int = 40) -> str:
    clean = [float(v or 0) for v in values]
    lo, hi = min(clean), max(clean)
    span = (hi - lo) or 1.0
    step = width / max(1, len(clean) - 1)
    points = [(i * step, height - 2 - ((v - lo) / span) * (height - 4)) for i, v in enumerate(clean)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = line + f" L{points[-1][0]:.1f},{height} L0,{height} Z"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">'
        f'<path class="a" d="{area}"/><path class="l" d="{line}"/></svg>'
    )


# -------------------------------------------------------------------- tables


def index_filters(
    tabs: list[tuple[str, str, int | None]],
    *,
    search_id: str,
    search_placeholder: str,
    sort_options: list[tuple[str, str]] | None = None,
    table_id: str = "tbl",
) -> str:
    """Polaris IndexFilters: tab pills, then the search and sort buttons.

    `tabs` is (label, filter key, count). Clicking a tab filters rows by
    `data-tab`. Sorting opens a Popover of the table's sortable columns.
    """
    tab_html = "".join(
        f'<button class="Polaris-Tabs__Tab{" Polaris-Tabs__Tab--active" if i == 0 else ""}" type="button" '
        f'data-tab="{esc(key)}" data-table="{esc(table_id)}" role="tab" aria-selected="{"true" if i == 0 else "false"}">'
        f'{esc(label)}{f"<span class=\"count\">{count}</span>" if count is not None else ""}</button>'
        for i, (label, key, count) in enumerate(tabs)
    )
    sort_html = ""
    if sort_options:
        items = "".join(
            f'<li><button class="Polaris-ActionList__Item" type="button" role="menuitemradio" '
            f'aria-checked="false" data-sort-col="{esc(col)}" data-table="{esc(table_id)}">'
            f'{esc(label)}{icon("check-small", 16, "check")}</button></li>'
            for label, col in sort_options
        )
        sort_html = (
            '<div style="position:relative">'
            + button("Sort", icon_name="sort", icon_only=True, attrs=f' data-popover="sort-{esc(table_id)}" aria-expanded="false" aria-haspopup="menu"')
            + f'<div class="Polaris-Popover Polaris-Popover--alignRight" id="sort-{esc(table_id)}" role="menu">'
            f'<ul class="Polaris-ActionList"><li class="Polaris-ActionList__Title">Sort by</li>{items}</ul></div></div>'
        )
    return (
        f'<div class="Polaris-IndexFilters" data-filters="{esc(table_id)}">'
        f'<div class="Polaris-Tabs" role="tablist">{tab_html}</div>'
        f'<div class="Polaris-IndexFilters__Search">{text_field(search_id, search_placeholder)}'
        + button("Cancel", variant="tertiary", attrs=' data-search-cancel="1"')
        + "</div>"
        f'<div class="Polaris-IndexFilters__Actions">'
        + button("Search and filter", icon_name="search", icon_only=True, attrs=' data-search-open="1"')
        + sort_html
        + "</div></div>"
    )


def index_table(
    columns: list[tuple[str, str, bool]],
    rows: list[str],
    empty_message: str,
    *,
    table_id: str = "tbl",
    empty_hint: str = "",
    paginate: bool = True,
) -> str:
    """Polaris IndexTable with client-side sorting and 50-row paging.

    `columns` is (label, alignment "" or "end", sortable). Each cell carries
    `data-sort` so numbers sort numerically. Rows carry `data-search` and
    `data-tab` for the filter bar.
    """
    heads = []
    for index, (label, align, can_sort) in enumerate(columns):
        cls = "Polaris-IndexTable__TableHeading"
        if align == "end":
            cls += " Polaris-IndexTable__TableHeading--align-end"
        if can_sort:
            cls += " Polaris-IndexTable__TableHeading--sortable"
        attrs = f' data-col="{index}" tabindex="0"' if can_sort else ""
        arrow = icon("arrow-down", 12, "Polaris-IndexTable__SortIcon") if can_sort else ""
        heads.append(f'<th class="{cls}"{attrs} scope="col">{esc(label)}{arrow}</th>')
    if rows:
        body = "".join(rows)
    else:
        body = (
            f'<tr class="Polaris-IndexTable__EmptyRow"><td colspan="{len(columns)}">'
            f"{empty(empty_message, empty_hint)}</td></tr>"
        )
    total = len(rows)
    footer = ""
    if paginate and total > PAGE_SIZE:
        footer = (
            f'<div class="Polaris-Card__Footer" data-pager="{esc(table_id)}">'
            f'<span class="Polaris-Pagination__Label">1-{min(PAGE_SIZE, total)} of {total}</span>'
            '<div class="Polaris-Pagination"><div class="Polaris-ButtonGroup Polaris-ButtonGroup--segmented">'
            + button("Previous", icon_name="chevron-left", icon_only=True, attrs=' data-page="-1" disabled')
            + button("Next", icon_name="chevron-right", icon_only=True, attrs=' data-page="1"')
            + "</div></div></div>"
        )
    loading = (
        f'<div class="Polaris-IndexTable__LoadingPanel" id="loading-{esc(table_id)}"><div>'
        f'<span class="Polaris-Spinner Polaris-Spinner--sizeSmall">{spinner_svg()}</span><span>Loading</span></div></div>'
    )
    return (
        f'<div class="Polaris-IndexTable">{loading}<div class="Polaris-IndexTable__ScrollContainer">'
        f'<table class="Polaris-IndexTable__Table" id="{esc(table_id)}" data-searchable="1" data-page-size="{PAGE_SIZE}">'
        f"<thead><tr>{''.join(heads)}</tr></thead><tbody>{body}</tbody></table></div>{footer}</div>"
    )


def row(cells: list[str], *, search: str = "", tab: str = "all", href: str | None = None) -> str:
    attrs = f' data-search="{esc(search.lower())}" data-tab="{esc(tab)}"'
    if href:
        attrs += f' data-href="{esc(href)}"'
    return f'<tr class="Polaris-IndexTable__TableRow"{attrs}>{"".join(cells)}</tr>'


def cell(content: str, *, align: str = "", sort: object = None, primary: bool = False, flush: bool = False) -> str:
    cls = "Polaris-IndexTable__TableCell"
    if align == "end":
        cls += " Polaris-IndexTable__TableCell--align-end"
    if primary:
        cls += " Polaris-IndexTable__TableCell--primary"
    if flush:
        cls += " Polaris-IndexTable__TableCell--flush"
    s = f' data-sort="{esc(sort)}"' if sort is not None else ""
    return f'<td class="{cls}"{s}>{content}</td>'


def resource(title: str, meta: str, media: str, href: str | None = None, external: bool = False) -> str:
    """The thumbnail, title and meta line that leads a table row or a list item."""
    if href:
        target = ' target="_blank" rel="noopener"' if external else ""
        t = f'<a class="Resource__Title t" href="{esc(href)}"{target} data-tooltip="{esc(title)}">{esc(title)}</a>'
    else:
        t = f'<span class="Resource__Title">{esc(title)}</span>'
    return f'<div class="Resource">{media}<div class="Resource__Body">{t}<span class="Resource__Meta">{esc(meta)}</span></div></div>'


def spinner_svg() -> str:
    return (
        '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7.229 1.173a9.25 9.25 0 1 0 11.655 11.412 1.25 1.25 0 1 0-2.4-.698 6.75 6.75 0 1 1-8.506-8.329 1.25 1.25 0 1 0-.75-2.385z"/></svg>'
    )


def product_row(index: int, r, prefix: str = "") -> str:
    """One product line for the overview's top-movers list."""
    sub = " · ".join(str(part) for part in (r["seller_name"], r["category_name"], r["method"]) if part)
    return (
        '<div class="ListRow"><span class="ListRow__Rank">'
        f"{index:02d}</span>"
        + resource(r["title"], sub, thumb(r["image_url"]), href=f'{prefix}products/{r["product_id"]}.html')
        + f'<span class="ListRow__Num"><span class="a">{money(r["revenue"])}</span>'
        f'<span class="b">{short(r["units"])} units</span></span>'
        f'<span class="ListRow__Badge">{confidence_badge(r["confidence"], r["unattributed"])}</span></div>'
    )


def video_row(index: int, r, prefix: str = "", show_product: bool = True) -> str:
    title = r["title"] or r["product_title"] or "Untitled video"
    handle = f"@{r['author_name']}" if r["author_name"] else "unknown creator"
    sub = f"{handle} · {r['product_title']}" if show_product else handle
    share = r["share"] or 0
    return (
        '<div class="ListRow"><span class="ListRow__Rank">'
        f"{index:02d}</span>"
        + resource(title, sub, thumb(r["cover_image_url"], tall=True, glyph="play"), href=r["url"], external=True)
        + f'<span class="ListRow__Num"><span class="a">+{short(r["view_delta"])}</span>'
        f'<span class="b">{share * 100:.0f}% share</span>{progress(share)}</span></div>'
    )


LIST_CSS = """
<style>
.ListRow{display:flex;align-items:center;gap:var(--p-space-300);padding:var(--p-space-300) 0;border-top:var(--p-border-width-025) solid var(--p-color-border-secondary)}
.ListRow:first-child{border-top:0}
.ListRow__Rank{font-family:var(--p-font-family-mono);font-size:0.75rem;color:var(--p-color-text-secondary);width:1.5rem;flex:0 0 auto;font-variant-numeric:tabular-nums}
.ListRow .Resource{flex:1 1 auto;min-width:0}
.ListRow__Num{flex:0 0 auto;display:flex;flex-direction:column;align-items:flex-end;gap:0.125rem;text-align:right}
.ListRow__Num .a{font-size:0.8125rem;line-height:1.25rem;font-weight:var(--p-font-weight-semibold);font-variant-numeric:tabular-nums}
.ListRow__Num .b{font-size:0.75rem;line-height:1rem;color:var(--p-color-text-secondary);font-variant-numeric:tabular-nums}
.ListRow__Num .Polaris-ProgressBar{width:6rem;margin-top:0.125rem}
.ListRow__Badge{flex:0 0 auto}
</style>
"""

TABLE_SCRIPT = """
<script>
(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var tables = {};

  function state(table) {
    if (!tables[table.id]) tables[table.id] = { page: 0, q: "", tab: "all", size: Number(table.dataset.pageSize) || 50 };
    return tables[table.id];
  }

  function flash(table) {
    var panel = document.getElementById("loading-" + table.id);
    if (!panel || reduce) return;
    panel.classList.add("on");
    setTimeout(function () { panel.classList.remove("on"); }, 350);
  }

  function apply(table) {
    var s = state(table), tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) { return r.classList.contains("Polaris-IndexTable__TableRow"); });
    var visible = rows.filter(function (r) {
      var okTab = s.tab === "all" || (r.dataset.tab || "").split(" ").indexOf(s.tab) !== -1;
      var okQ = !s.q || (r.dataset.search || "").indexOf(s.q) !== -1;
      return okTab && okQ;
    });
    rows.forEach(function (r) { r.hidden = true; });
    var start = s.page * s.size, end = start + s.size;
    visible.slice(start, end).forEach(function (r) { r.hidden = false; });
    var pager = document.querySelector("[data-pager='" + table.id + "']");
    if (pager) {
      pager.style.display = visible.length > s.size ? "" : "none";
      pager.querySelector(".Polaris-Pagination__Label").textContent =
        visible.length ? (start + 1) + "-" + Math.min(end, visible.length) + " of " + visible.length : "0 of 0";
      pager.querySelector("[data-page='-1']").disabled = s.page === 0;
      pager.querySelector("[data-page='1']").disabled = end >= visible.length;
    }
    var emptyRow = tbody.querySelector(".Polaris-IndexTable__EmptyRow--filtered");
    if (!visible.length && rows.length) {
      if (!emptyRow) {
        emptyRow = document.createElement("tr");
        emptyRow.className = "Polaris-IndexTable__EmptyRow Polaris-IndexTable__EmptyRow--filtered";
        emptyRow.innerHTML = "<td colspan='" + table.tHead.rows[0].cells.length + "'>No rows match. Clear the search or pick another tab.</td>";
        tbody.appendChild(emptyRow);
      }
    } else if (emptyRow) { emptyRow.remove(); }
  }

  function sortBy(table, col, dir) {
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) { return r.classList.contains("Polaris-IndexTable__TableRow"); });
    rows.sort(function (a, b) {
      var av = a.cells[col] ? a.cells[col].dataset.sort : "", bv = b.cells[col] ? b.cells[col].dataset.sort : "";
      var an = parseFloat(av), bn = parseFloat(bv), cmp;
      if (!isNaN(an) && !isNaN(bn)) cmp = an - bn; else cmp = String(av).localeCompare(String(bv));
      return dir === "ascending" ? cmp : -cmp;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
    table.querySelectorAll("th").forEach(function (o) { o.removeAttribute("aria-sort"); });
    var th = table.tHead.rows[0].cells[col];
    if (th) th.setAttribute("aria-sort", dir);
    state(table).page = 0;
    flash(table);
    apply(table);
  }

  document.querySelectorAll("table[data-searchable]").forEach(function (table) {
    apply(table);
    table.querySelectorAll("th.Polaris-IndexTable__TableHeading--sortable").forEach(function (th) {
      var go = function () {
        var col = Number(th.dataset.col);
        var dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        sortBy(table, col, dir);
      };
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    table.addEventListener("click", function (e) {
      var tr = e.target.closest("tr[data-href]");
      if (tr && !e.target.closest("a, button")) location.href = tr.dataset.href;
    });
  });

  document.querySelectorAll("[data-pager]").forEach(function (pager) {
    var table = document.getElementById(pager.dataset.pager);
    pager.querySelectorAll("[data-page]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state(table).page += Number(btn.dataset.page);
        flash(table); apply(table);
        table.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
      });
    });
  });

  document.querySelectorAll(".Polaris-Tabs__Tab[data-table]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var table = document.getElementById(tab.dataset.table);
      tab.parentNode.querySelectorAll(".Polaris-Tabs__Tab").forEach(function (t) { t.classList.remove("Polaris-Tabs__Tab--active"); t.setAttribute("aria-selected", "false"); });
      tab.classList.add("Polaris-Tabs__Tab--active"); tab.setAttribute("aria-selected", "true");
      var s = state(table); s.tab = tab.dataset.tab; s.page = 0;
      flash(table); apply(table);
    });
  });

  document.querySelectorAll("[data-sort-col]").forEach(function (item) {
    item.addEventListener("click", function () {
      var table = document.getElementById(item.dataset.table);
      item.closest(".Polaris-ActionList").querySelectorAll("[role=menuitemradio]").forEach(function (i) { i.setAttribute("aria-checked", "false"); });
      item.setAttribute("aria-checked", "true");
      sortBy(table, Number(item.dataset.sortCol), "descending");
    });
  });

  function wireSearch(input, table) {
    var field = input.closest(".Polaris-TextField");
    var run = function () {
      var s = state(table); s.q = input.value.trim().toLowerCase(); s.page = 0;
      if (field) field.classList.toggle("Polaris-TextField--hasValue", !!input.value);
      apply(table);
    };
    input.addEventListener("input", run);
    if (field) {
      var clear = field.querySelector(".Polaris-TextField__ClearButton");
      if (clear) clear.addEventListener("click", function () { input.value = ""; run(); input.focus(); });
    }
    run();
  }
  document.querySelectorAll(".Polaris-IndexFilters").forEach(function (bar) {
    var table = document.getElementById(bar.dataset.filters);
    var input = bar.querySelector("input[type=search]");
    var open = bar.querySelector("[data-search-open]"), cancel = bar.querySelector("[data-search-cancel]");
    if (input) wireSearch(input, table);
    if (open) open.addEventListener("click", function () { bar.classList.add("Polaris-IndexFilters--searching"); input.focus(); });
    if (cancel) cancel.addEventListener("click", function () { input.value = ""; input.dispatchEvent(new Event("input")); bar.classList.remove("Polaris-IndexFilters--searching"); });
  });
  var top = document.getElementById("search"), first = document.querySelector("table[data-searchable]");
  if (top && first) {
    wireSearch(top, first);
    var bar = document.querySelector(".Polaris-IndexFilters input[type=search]");
    top.addEventListener("input", function () { if (bar && bar.value !== top.value) { bar.value = top.value; bar.dispatchEvent(new Event("input")); } });
  }
})();
</script>
"""
