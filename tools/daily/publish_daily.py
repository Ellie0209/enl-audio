#!/usr/bin/env python3
"""Build complete Daily releases and publish without rebasing generated binaries."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from publication import ROOT, read_days, validate_all

SOURCES = ("tools/daily", ".github/workflows/shadow-daily.yml", "shadow/daily/d*/scripts.json")
ASSET = re.compile(r"shadow/daily/l[1-4]/d[0-9]{3}/(?:\.(?:lines\.sha1|worksheet\.sha256)|(?:us|uk)-(?:1|2|slow)\.mp3|ShadowShine_Daily_D[0-9]{3}_L[1-4]_[A-Za-z]+\.pdf)$")
CATALOG = ("index.html", "shadow/daily/index.html", "shadow/daily/index.json")


def git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True, text=True)


def changed_paths(root):
    tracked = git(root, "diff", "HEAD", "--name-only", "-z").stdout
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    return sorted(set(filter(None, (tracked + untracked).split("\0"))))


def assert_same_sources(root, base, tip):
    changed = git(root, "diff", "--name-only", base, tip, "--", *SOURCES).stdout.strip()
    if changed:
        raise RuntimeError("Daily sources changed during generation; discard these outputs and rebuild from main:\n" + changed)


def publish_generated(root=ROOT, attempts=3, remote="origin", branch="main"):
    """Overlay validated outputs on the latest main in a disposable worktree.

    A moved main is retried only while all Daily sources are unchanged. Root index
    edits are retained by rebuilding its Daily block on the latest checkout.
    No force-push, binary rebase, or replacement of scripts is permitted.
    """
    root = Path(root)
    base = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "diff", "--exit-code", "HEAD", "--", *SOURCES)
    with tempfile.TemporaryDirectory(prefix="shadow-publish-") as tmp:
        tmp = Path(tmp)
        payload = tmp / "payload"
        assets = [p for p in changed_paths(root) if ASSET.fullmatch(p)]
        for rel in assets:
            source = root / rel
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Refusing missing/symlink asset: {rel}")
            dest = payload / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        for attempt in range(1, attempts + 1):
            git(root, "fetch", remote, f"refs/heads/{branch}")
            tip = git(root, "rev-parse", "FETCH_HEAD").stdout.strip()
            assert_same_sources(root, base, tip)
            work = tmp / f"attempt-{attempt}"
            git(root, "worktree", "add", "--detach", str(work), tip)
            try:
                for rel in assets:
                    dest = work / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(payload / rel, dest)
                validate_all(work)
                subprocess.run([sys.executable, str(work / "tools/daily/build_pages.py"), "--strict"], cwd=work, check=True)
                generated = [p for p in changed_paths(work) if ASSET.fullmatch(p) or p in CATALOG
                             or re.fullmatch(r"shadow/daily/l[1-4]/d[0-9]{3}/index.html", p)]
                if not generated:
                    print(f"Already published: {tip}")
                    return tip
                git(work, "add", "--", *generated)
                git(work, "-c", "user.name=github-actions[bot]", "-c",
                    "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m",
                    "Publish complete Shadow & Shine Daily audio, worksheets and catalog [skip ci]")
                sha = git(work, "rev-parse", "HEAD").stdout.strip()
                result = git(work, "push", remote, f"HEAD:refs/heads/{branch}", check=False)
                if result.returncode == 0:
                    print(f"Published complete release: {sha}")
                    return sha
                git(root, "fetch", remote, f"refs/heads/{branch}")
                latest = git(root, "rev-parse", "FETCH_HEAD").stdout.strip()
                if latest == tip:
                    raise RuntimeError("Push failed without a concurrent commit:\n" + result.stderr)
                assert_same_sources(root, base, latest)
                if attempt == attempts:
                    raise RuntimeError(f"main moved during all {attempts} publication attempts; no force push was used")
                print(f"main moved; retrying publication ({attempt + 1}/{attempts})", flush=True)
            finally:
                git(root, "worktree", "remove", "--force", str(work))
            time.sleep(attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    git(ROOT, "diff", "--exit-code", "HEAD", "--", *SOURCES)
    read_days()
    extra = ["--force"] if args.force else []
    subprocess.run([sys.executable, str(ROOT / "tools/daily/build_audio.py"), *extra], check=True)
    subprocess.run([sys.executable, str(ROOT / "tools/daily/build_worksheets.py"), "--all", *extra], check=True)
    validate_all(media=True)
    sha = publish_generated()
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"published_sha={sha}\n")


if __name__ == "__main__":
    main()
