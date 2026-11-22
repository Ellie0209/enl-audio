import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / "tools/daily"))
import check_daily
import publication
import publish_daily


def pdf_bytes():
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>"]
    for number in (3, 5, 7):
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {number+1} 0 R /Resources << /Font << /F1 9 0 R >> >> >>".encode())
        stream = b"BT /F1 16 Tf 40 700 Td (Daily worksheet test) Tj ET"
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return out + f"trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{xref}\n%%EOF\n".encode()


def scripts(day=1, date="2026-11-22"):
    sc = {"title": "A New Day", "title_kr": "새로운 날", "genre": "Story", "topic": "family",
          "lines": ["A *new* day. ↘"], "targets": ["day"], "vocab": [["day", "날"]],
          "sounds": [["ay", "day", "long a"]], "expression": "Read warmly.", "practice": ["new day"], "events": []}
    return {"day": day, "date": date, "scripts": {str(lv): copy.deepcopy(sc) for lv in range(1, 5)}}


def fixture(root, d=None):
    d = d or scripts()
    target = root / "tools/daily"
    target.mkdir(parents=True)
    for path in (SOURCE / "tools/daily").glob("*.py"):
        shutil.copyfile(path, target / path.name)
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    sp = root / "shadow/daily" / f"d{d['day']:03d}/scripts.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps(d))
    (root / "index.html").write_text('<h1>Audio</h1><h3>Speak Up!</h3>')
    for lv, sc in d["scripts"].items():
        out = publication.level_dir(root, d, lv)
        out.mkdir(parents=True)
        for name in publication.TRACK_NAMES:
            (out / name).write_bytes(b"ID3" + b"a" * 1100)
        (out / publication.pdf_name(d, lv)).write_bytes(pdf_bytes())
        (out / ".lines.sha1").write_text(publication.audio_digest(sc, lv))
        (out / ".worksheet.sha256").write_text(publication.worksheet_digest(d, lv, root))
    subprocess.run([sys.executable, str(target / "build_pages.py"), "--strict"], check=True, capture_output=True)
    return d


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.day = fixture(self.root)

    def test_complete_day_passes_and_has_four_levels(self):
        self.assertEqual(publication.validate_all(self.root), [self.day])
        publication.check_pdf(publication.level_dir(self.root, self.day, "1") / publication.pdf_name(self.day, "1"))

    def test_missing_pdf_is_never_added_to_catalog(self):
        (publication.level_dir(self.root, self.day, "4") / publication.pdf_name(self.day, "4")).unlink()
        old = (self.root / "shadow/daily/index.json").read_bytes()
        command = [sys.executable, str(self.root / "tools/daily/build_pages.py")]
        result = subprocess.run(command + ["--strict"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "shadow/daily/index.json").read_bytes(), old)
        # Before the first migration, an external premature build must not erase the old catalog.
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual((self.root / "shadow/daily/index.json").read_bytes(), old)

    def test_new_incomplete_day_is_excluded_while_old_complete_day_remains(self):
        next_day = scripts(2, "2026-11-23")
        path = self.root / "shadow/daily/d002/scripts.json"
        path.parent.mkdir()
        path.write_text(json.dumps(next_day))
        subprocess.run([sys.executable, str(self.root / "tools/daily/build_pages.py")], check=True, capture_output=True)
        index = json.loads((self.root / "shadow/daily/index.json").read_text())
        self.assertEqual([d["day"] for d in index], [1])

    def test_text_and_metadata_changes_invalidate_the_right_assets(self):
        edited = copy.deepcopy(self.day)
        edited["scripts"]["1"]["expression"] = "Different teacher guidance."
        self.assertIn(".worksheet.sha256", "\n".join(publication.asset_errors(edited, self.root)))
        self.assertNotIn(".lines.sha1", "\n".join(publication.asset_errors(edited, self.root)))
        edited["scripts"]["1"]["lines"] = ["A different line."]
        self.assertIn(".lines.sha1", "\n".join(publication.asset_errors(edited, self.root)))

    def test_invalid_or_duplicate_dates_and_missing_levels_are_rejected(self):
        path = self.root / "shadow/daily/d002/scripts.json"
        path.parent.mkdir()
        d = scripts(2)
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            publication.read_days(self.root)
        d["date"] = "2026-11-23"
        del d["scripts"]["4"]
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "levels"):
            publication.read_days(self.root)

    def test_monitor_distinguishes_missing_source_assets_and_catalog(self):
        self.assertEqual(check_daily.local_release(self.root, "2026-11-23")[0], "source_missing")
        self.assertEqual(check_daily.local_release(self.root, "2026-11-22")[0], "ok")
        index = self.root / "shadow/daily/index.json"
        index.write_text("[]")
        self.assertEqual(check_daily.local_release(self.root, "2026-11-22")[0], "catalog_incomplete")
        (publication.level_dir(self.root, self.day, "1") / "uk-slow.mp3").unlink()
        self.assertEqual(check_daily.local_release(self.root, "2026-11-22")[0], "asset_incomplete")

    def test_public_check_compares_all_asset_bytes(self):
        called = []
        def fetch(url, limit=None):
            rel = url.removeprefix(check_daily.BASE).split("?")[0]
            called.append(rel)
            return (self.root / rel).read_bytes()
        self.assertEqual(check_daily.public_release(self.day, self.root, fetch=fetch)[0], "ok")
        self.assertEqual(len(called), 30) # catalog + scripts + 24 audio + 4 PDF
        def corrupt(url, limit=None):
            return b"wrong audio" if url.endswith("us-1.mp3") else fetch(url, limit)
        self.assertEqual(check_daily.public_release(self.day, self.root, fetch=corrupt)[0], "public_asset_mismatch")
        def missing(url, limit=None):
            if url.endswith("uk-slow.mp3"):
                raise urllib.error.HTTPError(url, 404, "missing", {}, None)
            return fetch(url, limit)
        self.assertEqual(check_daily.public_release(self.day, self.root, fetch=missing)[0], "public_asset_unavailable")

    def test_stale_public_index_is_not_success(self):
        self.assertEqual(check_daily.public_release(self.day, self.root, fetch=lambda url: b"[]")[0], "public_stale")

    def test_scheduled_check_keeps_expected_date_after_kst_midnight(self):
        self.assertEqual(check_daily.scheduled_date(datetime(2026, 11, 22, 15, 10, tzinfo=timezone.utc)), "2026-11-22")
        self.assertEqual(check_daily.scheduled_date(datetime(2026, 11, 23, 0, 5, tzinfo=timezone.utc)), "2026-11-22")
        self.assertEqual(check_daily.scheduled_date(datetime(2026, 11, 23, 14, 50, tzinfo=timezone.utc)), "2026-11-23")


class GitPublication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "build"
        self.root.mkdir()
        self.day = fixture(self.root)
        self.remote = self.base / "remote.git"
        self.editor = self.base / "editor"
        self.run_git(self.base, "init", "--bare", str(self.remote))
        self.run_git(self.root, "init", "-b", "main")
        self.run_git(self.root, "config", "user.name", "Test")
        self.run_git(self.root, "config", "user.email", "test@example.invalid")
        self.run_git(self.root, "add", ".")
        self.run_git(self.root, "commit", "-m", "baseline")
        self.run_git(self.root, "remote", "add", "origin", str(self.remote))
        self.run_git(self.root, "push", "-u", "origin", "main")
        self.run_git(self.base, "clone", "--branch", "main", str(self.remote), str(self.editor))
        self.run_git(self.editor, "config", "user.name", "Other writer")
        self.run_git(self.editor, "config", "user.email", "other@example.invalid")
        self.audio_rel = "shadow/daily/l1/d001/us-1.mp3"

    def run_git(self, root, *args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def edit_remote(self, path, text):
        (self.editor / path).write_text(text)
        self.run_git(self.editor, "add", path)
        self.run_git(self.editor, "commit", "-m", "concurrent change")
        self.run_git(self.editor, "push", "origin", "main")

    def test_publish_and_idempotent_noop(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        sha = publish_daily.publish_generated(self.root)
        self.assertEqual(self.run_git(self.root, "ls-remote", "origin", "refs/heads/main").split()[0], sha)
        self.run_git(self.editor, "pull", "--ff-only")
        self.assertEqual((self.editor / self.audio_rel).read_bytes(), (self.root / self.audio_rel).read_bytes())
        # Use the clean, published clone for a truly unchanged run.
        self.assertEqual(publish_daily.publish_generated(self.editor), sha)

    def test_concurrent_unrelated_commit_is_preserved_on_retry(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        original, raced = publish_daily.git, False
        def race(root, *args, **kwargs):
            nonlocal raced
            if args[0] == "push" and not raced:
                raced = True
                self.edit_remote("index.html", (self.editor / "index.html").read_text() + "<p>Unrelated change</p>")
            return original(root, *args, **kwargs)
        with patch.object(publish_daily, "git", side_effect=race), patch.object(publish_daily.time, "sleep"):
            publish_daily.publish_generated(self.root)
        self.run_git(self.editor, "pull", "--ff-only")
        self.assertIn("Unrelated change", (self.editor / "index.html").read_text())
        self.assertEqual((self.editor / self.audio_rel).read_bytes(), (self.root / self.audio_rel).read_bytes())

    def test_concurrent_script_edit_rejects_stale_outputs(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        original, raced = publish_daily.git, False
        def race(root, *args, **kwargs):
            nonlocal raced
            if args[0] == "push" and not raced:
                raced = True
                d = copy.deepcopy(self.day)
                d["scripts"]["1"]["lines"] = ["The source changed during generation."]
                self.edit_remote("shadow/daily/d001/scripts.json", json.dumps(d))
            return original(root, *args, **kwargs)
        with patch.object(publish_daily, "git", side_effect=race):
            with self.assertRaisesRegex(RuntimeError, "sources changed"):
                publish_daily.publish_generated(self.root)
        remote_audio = subprocess.run(["git", "show", "main:" + self.audio_rel], cwd=self.remote, capture_output=True, check=True).stdout
        self.assertNotEqual(remote_audio, (self.root / self.audio_rel).read_bytes())

    def test_commit_failure_is_not_hidden_as_nothing_to_commit(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        original = publish_daily.git
        def fail(root, *args, **kwargs):
            if "commit" in args:
                raise subprocess.CalledProcessError(1, ["git", "commit"])
            return original(root, *args, **kwargs)
        before = self.run_git(self.remote, "rev-parse", "main")
        with patch.object(publish_daily, "git", side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                publish_daily.publish_generated(self.root)
        self.assertEqual(self.run_git(self.remote, "rev-parse", "main"), before)

    def test_push_permission_failure_is_not_retried_as_a_race(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        original, pushes = publish_daily.git, 0
        def fail(root, *args, **kwargs):
            nonlocal pushes
            if args[0] == "push":
                pushes += 1
                return subprocess.CompletedProcess(["git", "push"], 1, "", "permission denied")
            return original(root, *args, **kwargs)
        with patch.object(publish_daily, "git", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "without a concurrent commit"):
                publish_daily.publish_generated(self.root)
        self.assertEqual(pushes, 1)

    def test_concurrent_retries_stop_at_the_configured_limit(self):
        (self.root / self.audio_rel).write_bytes(b"ID3" + b"b" * 1200)
        original, pushes = publish_daily.git, 0
        def race(root, *args, **kwargs):
            nonlocal pushes
            if args[0] == "push":
                pushes += 1
                self.edit_remote("index.html", (self.editor / "index.html").read_text() + f"<p>Concurrent {pushes}</p>")
            return original(root, *args, **kwargs)
        with patch.object(publish_daily, "git", side_effect=race), patch.object(publish_daily.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "all 2 publication attempts"):
                publish_daily.publish_generated(self.root, attempts=2)
        self.assertEqual(pushes, 2)


if __name__ == "__main__":
    unittest.main()
