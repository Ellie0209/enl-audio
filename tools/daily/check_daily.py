#!/usr/bin/env python3
"""Classify missing inputs, incomplete assets, and stale public Daily releases."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from publication import ROOT, TRACK_NAMES, asset_errors, level_dir, pdf_name, read_days

BASE = "https://ellie0209.github.io/enl-audio/"


def scheduled_date(now=None):
    """Most recent 14:50 UTC slot (=23:50 KST), including delays past midnight."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    slot = now.replace(hour=14, minute=50, second=0, microsecond=0)
    if now < slot:
        slot -= timedelta(days=1)
    return slot.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()


def state_entry(d):
    return {"day": d["day"], "date": d["date"], "levels": {
        lv: {"title": sc["title"], "topic": sc["topic"], "genre": sc["genre"]}
        for lv, sc in d["scripts"].items()}}


def read_remote(url, limit=5_000_000):
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "ShadowDaily-healthcheck"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Unexpected response size: {url}")
        return data


def local_release(root=ROOT, target=None):
    try:
        days = read_days(root)
    except (ValueError, KeyError, OSError) as exc:
        return "input_invalid", [str(exc)], None
    candidates = [d for d in days if d["date"] == target] if target else days[-1:]
    if not candidates:
        return "source_missing", [f"No scripts registered for {target}; the external content job has not supplied this date"], None
    d = candidates[0]
    errors = asset_errors(d, root)
    if errors:
        return "asset_incomplete", errors, d
    try:
        index = json.loads((Path(root) / "shadow/daily/index.json").read_text())
        if not isinstance(index, list) or state_entry(d) not in index:
            return "catalog_incomplete", ["Complete assets exist, but their current entry is absent from index.json"], d
    except (OSError, ValueError) as exc:
        return "catalog_incomplete", [str(exc)], d
    return "ok", [], d


def public_release(d, root=ROOT, base=BASE, fetch=read_remote):
    """Verify source/catalog equality and exact bytes of all 28 public assets."""
    try:
        suffix = f"?daily_check={time.time_ns()}"
        index = json.loads(fetch(base + "shadow/daily/index.json" + suffix))
        script = json.loads(fetch(base + f"shadow/daily/d{d['day']:03d}/scripts.json" + suffix))
        if not isinstance(index, list) or state_entry(d) not in index or script != d:
            return "public_stale", ["Public scripts/catalog do not match the repository release"]
    except (OSError, ValueError) as exc:
        return "public_stale", [str(exc)]

    def check(path):
        rel = path.relative_to(root).as_posix()
        try:
            expected = path.read_bytes()
            actual = fetch(base + rel, limit=len(expected))
            if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
                return "public_asset_mismatch", f"{rel}: public bytes differ from this release"
        except (OSError, ValueError) as exc:
            return "public_asset_unavailable", f"{rel}: {exc}"
        return None

    paths = [level_dir(root, d, lv) / name for lv in d["scripts"] for name in (*TRACK_NAMES, pdf_name(d, lv))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        errors = [e for e in pool.map(check, paths) if e]
    if errors:
        return errors[0][0], [e[1] for e in errors]
    return "ok", [f"d{d['day']:03d} {d['date']}: public catalog, scripts, 24 MP3s and 4 PDFs match"]


def report(status, details, target):
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    lines = ["## Shadow & Shine Daily publication check", f"- Checked: {stamp}",
             f"- Target: {target or 'latest registered date'}", f"- Result: **{status}**", *[f"- {line}" for line in details]]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            out.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Expected publication date (YYYY-MM-DD, KST)")
    parser.add_argument("--scheduled", action="store_true", help="check the most recent 23:50 KST publication deadline")
    parser.add_argument("--latest", action="store_true", help="verify the latest registered date after publishing")
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait for public deployment/CDN propagation")
    args = parser.parse_args()
    target = args.date or (scheduled_date() if args.scheduled else None)
    if not target and not args.latest:
        target = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    status, details, d = local_release(target=target)
    if status == "ok":
        deadline = time.monotonic() + args.wait
        while True:
            status, details = public_release(d)
            if status == "ok" or time.monotonic() >= deadline:
                break
            time.sleep(min(10, max(0, deadline - time.monotonic())))
    report(status, details, target)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
