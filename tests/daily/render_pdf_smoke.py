"""Render real scripts without publishing, calling TTS, or modifying the catalog."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/daily"))
from publication import check_pdf, pdf_name
from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "tools/daily/build_worksheets.py"), str(args.day), args.out], check=True)
    d = json.loads((ROOT / f"shadow/daily/d{args.day:03d}/scripts.json").read_text())
    for lv, sc in d["scripts"].items():
        path = Path(args.out) / pdf_name(d, lv)
        check_pdf(path)
        reader = PdfReader(path)
        text = " ".join(p.extract_text() or "" for p in reader.pages)
        assert sc["title"] in text, f"L{lv}: missing English title"
        assert sc["title_kr"] in text, f"L{lv}: missing Korean title/font"
        assert d["date"] in text, f"L{lv}: missing publication date"
        assert "Dictation" in text and "Teacher Script" in text, f"L{lv}: missing worksheet sections"
        print(f"L{lv}: {len(reader.pages)} pages, English/Korean titles and worksheet sections verified")


if __name__ == "__main__":
    main()
