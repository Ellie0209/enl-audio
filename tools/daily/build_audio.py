#!/usr/bin/env python3
"""Shadow & Shine Daily — audio builder (runs in GitHub Actions, see .github/workflows/shadow-daily.yml).

For every shadow/daily/dNNN/scripts.json and every level it writes, to shadow/daily/l{lv}/dNNN/:
  us-1.mp3  normal      us-slow.mp3  slow      us-2.mp3  echo (phrase by phrase with pauses, then the whole line)
  uk-1.mp3  normal      uk-slow.mp3  slow      uk-2.mp3  echo
A level is (re)built when any of the 6 files is missing or the script lines changed (.lines.sha1).
Voices are fixed so every day sounds the same — see tools/daily/README.md.
"""
import glob, hashlib, json, os, re, subprocess, sys, tempfile

import numpy as np
import soundfile as sf

SR = 24000
VOICES = {"us": ("a", "af_heart"), "uk": ("b", "bf_emma")}
# normal speaking speed per level (Kokoro speed factor); slow = normal * SLOW
SPEED = {"1": 0.85, "2": 0.9, "3": 0.95, "4": 1.0}
SLOW = 0.8
GAP = {"1": 0.9, "2": 0.8, "3": 0.7, "4": 0.65}  # silence between lines (s), normal track

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_pipes = {}


def clean(t):
    t = t.replace("*", "").replace("↗", "").replace("↘", "")
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    t = t.replace("—", ", ").replace("…", "...")
    t = re.sub(r"\s*\|\s*", " ", t)
    return re.sub(r"\s+", " ", t).strip().strip(",").strip()


def phrases(line):
    out = [clean(p).replace('"', "").strip() for p in line.split("|")]
    return [p for p in out if p]


def tts(acc, text, speed):
    from kokoro import KPipeline
    lang, voice = VOICES[acc]
    if lang not in _pipes:
        _pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    out = []
    for _, _, audio in _pipes[lang](text, voice=voice, speed=speed):
        if audio is not None:
            out.append(np.asarray(audio, dtype=np.float32))
    a = np.concatenate(out) if out else np.zeros(int(SR * 0.3), np.float32)
    # trim leading/trailing near-silence so our own gaps are exact
    idx = np.where(np.abs(a) > 0.01)[0]
    if len(idx):
        a = a[max(0, idx[0] - int(0.03 * SR)): idx[-1] + int(0.08 * SR)]
    return a


def sil(sec):
    return np.zeros(int(SR * sec), np.float32)


def track_normal(acc, lines, speed, gap):
    parts = [sil(0.4)]
    for ln in lines:
        parts += [tts(acc, clean(ln), speed), sil(gap)]
    return np.concatenate(parts)


def track_echo(acc, lines, speed):
    parts = [sil(0.4)]
    for ln in lines:
        ph = phrases(ln)
        if len(ph) > 1:
            for p in ph:
                a = tts(acc, p, speed)
                parts += [a, sil(len(a) / SR * 1.2 + 0.8)]
        a = tts(acc, clean(ln), speed)
        parts += [a, sil(len(a) / SR * 1.1 + 1.2)]
    return np.concatenate(parts)


def write_mp3(a, path):
    a = a / max(1e-6, float(np.max(np.abs(a)))) * 0.89
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = f.name
    sf.write(wav, a, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-ac", "1", "-ar", str(SR),
                    "-codec:a", "libmp3lame", "-b:a", "96k", path], check=True)
    os.remove(wav)


def main():
    force = "--force" in sys.argv
    built = 0
    for sp in sorted(glob.glob(os.path.join(ROOT, "shadow/daily/d[0-9][0-9][0-9]/scripts.json"))):
        d = json.load(open(sp, encoding="utf-8"))
        nnn = "d%03d" % d["day"]
        for lv, sc in sorted(d["scripts"].items()):
            out = os.path.join(ROOT, "shadow/daily", "l" + lv, nnn)
            os.makedirs(out, exist_ok=True)
            sha = hashlib.sha1(json.dumps([sc["lines"], VOICES, SPEED[lv], SLOW]).encode()).hexdigest()
            shaf = os.path.join(out, ".lines.sha1")
            names = [f"{a}-{k}.mp3" for a in VOICES for k in ("1", "slow", "2")]
            have = all(os.path.exists(os.path.join(out, n)) and os.path.getsize(os.path.join(out, n)) > 1000 for n in names)
            if have and not force and os.path.exists(shaf) and open(shaf).read().strip() == sha:
                print(f"skip {nnn} L{lv}")
                continue
            for acc in VOICES:
                print(f"build {nnn} L{lv} {acc}", flush=True)
                write_mp3(track_normal(acc, sc["lines"], SPEED[lv], GAP[lv]), os.path.join(out, f"{acc}-1.mp3"))
                write_mp3(track_normal(acc, sc["lines"], SPEED[lv] * SLOW, GAP[lv] * 1.4), os.path.join(out, f"{acc}-slow.mp3"))
                write_mp3(track_echo(acc, sc["lines"], SPEED[lv] * 0.95), os.path.join(out, f"{acc}-2.mp3"))
            open(shaf, "w").write(sha + "\n")
            built += 1
    print(f"built {built} level-day(s)")


if __name__ == "__main__":
    main()
