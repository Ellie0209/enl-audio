"""Shared input and asset checks for the Daily publisher (no TTS imports)."""
import hashlib
import json
import math
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEVEL_NAMES = {"1": "Sprout", "2": "Seedling", "3": "Sapling", "4": "Tree"}
VOICES = {"us": ("a", "af_heart"), "uk": ("b", "bf_emma")}
SPEED = {"1": 0.72, "2": 0.75, "3": 0.75, "4": 0.8}
SLOW = 0.8
GAP = {"1": 1.5, "2": 1.3, "3": 1.2, "4": 0.8}
TRACK_NAMES = tuple(f"{a}-{k}.mp3" for a in VOICES for k in ("1", "slow", "2"))


def read_days(root=ROOT):
    days, dates = [], set()
    for path in sorted((Path(root) / "shadow/daily").glob("d[0-9][0-9][0-9]/scripts.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        day = d.get("day")
        if type(day) is not int or not 1 <= day <= 999 or path.parent.name != f"d{day:03d}":
            raise ValueError(f"{path}: day must match its directory (1–999)")
        if date.fromisoformat(d["date"]).isoformat() != d["date"] or d["date"] in dates:
            raise ValueError(f"{path}: invalid or duplicate publication date")
        dates.add(d["date"])
        if not isinstance(d.get("scripts"), dict) or set(d["scripts"]) != set(LEVEL_NAMES):
            raise ValueError(f"{path}: exactly levels 1–4 are required")
        for lv, sc in d["scripts"].items():
            if not isinstance(sc, dict):
                raise ValueError(f"{path} L{lv}: script must be an object")
            for field in ("title", "title_kr", "genre", "topic", "expression"):
                if not isinstance(sc.get(field), str) or not sc[field].strip():
                    raise ValueError(f"{path} L{lv}: missing {field}")
            for field in ("lines", "targets", "practice"):
                values = sc.get(field)
                if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ValueError(f"{path} L{lv}: invalid {field}")
            for field, width in (("vocab", 2), ("sounds", 3)):
                values = sc.get(field)
                if not isinstance(values, list) or not values or any(
                    not isinstance(v, list) or len(v) != width or any(not isinstance(t, str) for t in v)
                    for v in values
                ):
                    raise ValueError(f"{path} L{lv}: invalid {field}")
            if not isinstance(sc.get("events"), list) or any(not isinstance(v, str) for v in sc["events"]):
                raise ValueError(f"{path} L{lv}: invalid events")
        days.append(d)
    if not days:
        raise ValueError("No Daily scripts found; refusing to publish an empty catalog")
    return days


def audio_digest(sc, lv):
    # Keep the original serialization so existing audio is reused unchanged.
    return hashlib.sha1(json.dumps([sc["lines"], VOICES, SPEED[lv], SLOW, GAP[lv]]).encode()).hexdigest()


def worksheet_digest(d, lv, root=ROOT):
    content = json.dumps([d["day"], d["date"], lv, d["scripts"][lv]], ensure_ascii=False, sort_keys=True).encode()
    template = (Path(root) / "tools/daily/build_worksheets.py").read_bytes()
    return hashlib.sha256(content + b"\0" + template).hexdigest()


def level_dir(root, d, lv):
    return Path(root) / "shadow/daily" / f"l{lv}" / f"d{d['day']:03d}"


def pdf_name(d, lv):
    return f"ShadowShine_Daily_D{d['day']:03d}_L{lv}_{LEVEL_NAMES[lv]}.pdf"


def has_signature(path, expected):
    return path.is_file() and path.read_text().strip() == expected


def check_pdf(path):
    from pypdf import PdfReader
    try:
        reader = PdfReader(path, strict=True)
        if len(reader.pages) < 3 or not all((p.extract_text() or "").strip() for p in reader.pages):
            raise ValueError("worksheet must contain at least 3 nonempty pages")
    except Exception as exc:
        raise ValueError(f"{path}: invalid worksheet PDF: {exc}") from exc


def check_audio(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
         "-of", "json", str(path)], check=True, capture_output=True, text=True, timeout=30)
    probe = json.loads(result.stdout)
    duration = float(probe.get("format", {}).get("duration", 0))
    streams = probe.get("streams", [])
    if not math.isfinite(duration) or duration <= 0 or not any(
        s.get("codec_name") == "mp3" and s.get("sample_rate") == "24000" and s.get("channels") == 1
        for s in streams
    ):
        raise ValueError(f"{path}: expected a nonempty 24kHz mono MP3")


def asset_errors(d, root=ROOT, media=False):
    errors = []
    for lv, sc in sorted(d["scripts"].items()):
        out = level_dir(root, d, lv)
        for name in (*TRACK_NAMES, pdf_name(d, lv)):
            path = out / name
            try:
                if not path.is_file() or path.stat().st_size <= 1000:
                    raise ValueError("missing or too small")
                with path.open("rb") as f:
                    prefix = f.read(5)
                if name.endswith(".pdf"):
                    if prefix != b"%PDF-":
                        raise ValueError("invalid PDF header")
                    if media:
                        check_pdf(path)
                elif media:
                    check_audio(path)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(f"{path.relative_to(root)}: {exc}")
        for name, expected in ((".lines.sha1", audio_digest(sc, lv)),
                               (".worksheet.sha256", worksheet_digest(d, lv, root))):
            try:
                if not has_signature(out / name, expected):
                    errors.append(f"d{d['day']:03d} L{lv}: missing/stale {name}")
            except (OSError, ValueError) as exc:
                errors.append(f"d{d['day']:03d} L{lv}: invalid {name}: {exc}")
    return errors


def validate_all(root=ROOT, media=False):
    days = read_days(root)
    errors = [e for d in days for e in asset_errors(d, root, media)]
    if errors:
        raise ValueError("Incomplete Daily assets:\n" + "\n".join(errors))
    return days
