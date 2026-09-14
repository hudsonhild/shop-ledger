"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
import uuid
import webbrowser
from pathlib import Path

from . import config, db, render, resolve, sweep
from .client import ApiError, Client, OutOfCredits
from .pull import persist_panel
from .pull import pull as pull_products

BANNER = "shop-ledger"


def _say(message: str) -> None:
    print(f"{BANNER}: {message}", flush=True)


def _client(cfg: config.Config) -> Client:
    return Client(cfg.api_key)


# ------------------------------------------------------------------ commands


def cmd_init(args: argparse.Namespace) -> int:
    cfg = config.load(require_key=False)
    conn = db.init(cfg.db_path)
    conn.close()
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    _say(f"database ready at {cfg.db_path}")
    if not cfg.api_key:
        _say("no API key yet. Copy .env.example to .env and add SCRAPECREATORS_API_KEY.")
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    cfg = config.load()
    client = _client(cfg)
    keywords = sweep.load_keywords(Path(args.keywords) if args.keywords else None)
    run_id = uuid.uuid4().hex[:12]

    with db.session(cfg.db_path) as conn:
        db.start_run(conn, run_id, "sweep", client.credits)
        result = sweep.sweep(conn, client, keywords)
        promoted = sweep.promote(conn, cfg.panel_size)
        db.finish_run(
            conn, run_id, client.credits, client.calls, len(result["failures"]), "sweep"
        )

    _say(
        f"swept {result['keywords']} keywords, saw {result['products']} products, "
        f"panel now {promoted['tracked']} (+{promoted['added']})"
    )
    if promoted["cold_start"]:
        _say("cold start: panel ranked by lifetime volume. Tomorrow it ranks by delta.")
    for failure in result["failures"]:
        _say(f"  warn {failure}")
    if client.credits is not None:
        _say(f"{client.credits:,} credits remaining")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    cfg = config.load()
    client = _client(cfg)
    run_id = uuid.uuid4().hex[:12]

    try:
        with db.session(cfg.db_path) as conn:
            db.start_run(conn, run_id, "pull", client.credits)
            result = pull_products(conn, client, cfg.min_credits)
            panel = persist_panel(
                conn, client, cfg.panel_window_days, cfg.min_credits, cfg.panel_budget
            )
            db.finish_run(
                conn, run_id, client.credits, client.calls, len(result["failures"]), "pull"
            )
    except OutOfCredits as exc:
        _say(f"aborted: {exc}")
        return 2

    _say(
        f"pulled {result['pulled']}/{result['of']} products, {result['videos']} videos"
    )
    if panel["orphans"]:
        _say(
            f"  panel persistence: re-sampled {panel['kept']}/{panel['orphans']} "
            f"videos that fell out of the top 18"
        )
    if result["missing"]:
        _say(f"  {len(result['missing'])} not available in the US region, skipped")
    for failure in result["failures"][:5]:
        _say(f"  warn {failure}")
    if client.credits is not None:
        _say(f"{client.credits:,} credits remaining")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    cfg = config.load(require_key=False)
    with db.session(cfg.db_path) as conn:
        result = resolve.resolve(conn, cfg)
    _say(
        f"resolved {result['written']} products, skipped {result['skipped']} "
        f"awaiting a second snapshot"
    )
    if result["restocks"]:
        _say(f"  {result['restocks']} restock flags, stock delta unusable on those rows")
    if result["low_confidence"]:
        _say(f"  {result['low_confidence']} rows below 0.3 confidence, reported as unattributed")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    cfg = config.load(require_key=False)
    credits = None
    if cfg.api_key and not args.offline:
        try:
            credits = _client(cfg).check_credits()
        except ApiError:
            credits = None

    out = Path(args.out) if args.out else cfg.out_dir / "index.html"
    with db.session(cfg.db_path) as conn:
        path = render.render(conn, out, credits)
    _say(f"dashboard written to {path}")
    if args.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    for step in (cmd_sweep, cmd_pull, cmd_resolve):
        code = step(args)
        if code != 0:
            return code
    return cmd_render(args)


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load(require_key=False)
    with db.session(cfg.db_path) as conn:
        counts = {
            "products seen": "SELECT COUNT(*) FROM product",
            "tracked panel": "SELECT COUNT(*) FROM product WHERE tier='tracked'",
            "product snapshots": "SELECT COUNT(*) FROM product_snapshot",
            "videos": "SELECT COUNT(*) FROM video",
            "resolved days": "SELECT COUNT(DISTINCT day) FROM daily_result",
        }
        for label, query in counts.items():
            _say(f"{label}: {conn.execute(query).fetchone()[0]:,}")
        last = conn.execute(
            "SELECT * FROM run_log ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if last:
            _say(
                f"last run {last['stage']} at {last['started_at']}, "
                f"{last['calls']} calls, {last['errors']} errors"
            )
    _say(f"database {cfg.db_path}")
    return 0


# --------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shop-ledger",
        description="A personal TikTok Shop product database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    p_sweep = sub.add_parser("sweep", help="discover products and promote the movers")
    p_sweep.add_argument("--keywords", help="path to a keyword file, one per line")
    p_sweep.set_defaults(func=cmd_sweep)

    sub.add_parser("pull", help="detail pull for the tracked panel").set_defaults(func=cmd_pull)
    sub.add_parser("resolve", help="compute units, revenue and attribution").set_defaults(
        func=cmd_resolve
    )

    p_render = sub.add_parser("render", help="write the dashboard")
    p_render.add_argument("--out", help="output path, defaults to <data-dir>/out/index.html")
    p_render.add_argument("--open", action="store_true", help="open it in a browser")
    p_render.add_argument("--offline", action="store_true", help="skip the credit check")
    p_render.set_defaults(func=cmd_render)

    p_run = sub.add_parser("run", help="sweep, pull, resolve and render in one go")
    p_run.add_argument("--keywords")
    p_run.add_argument("--out")
    p_run.add_argument("--open", action="store_true")
    p_run.add_argument("--offline", action="store_true")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("status", help="what is in the database").set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except config.ConfigError as exc:
        _say(str(exc))
        return 2
    except OutOfCredits as exc:
        _say(f"out of credits: {exc}")
        return 2
    except ApiError as exc:
        _say(f"api error: {exc}")
        return 1
    except KeyboardInterrupt:
        _say("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
