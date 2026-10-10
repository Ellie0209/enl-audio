"""Build Korean audio (Supertonic 3, voices F1 / M1) from tools/ko_manifest.json. Runs on GitHub Actions."""
import inspect, json, os, subprocess, sys, numpy as np, soundfile as sf
from supertonic import TTS
tts = TTS()
SR = getattr(tts, "sample_rate", 44100)
STY = {"F1": tts.get_voice_style(voice_name="F1"), "M1": tts.get_voice_style(voice_name="M1")}
sig = inspect.signature(tts.synthesize).parameters
print("synthesize params:", list(sig), "sr:", SR, flush=True)

def say(text, voice, speed):
    kw = {"voice_style": STY[voice], "lang": "ko"}
    if "speed" in sig: kw["speed"] = speed
    for k in ("total_steps", "total_step", "steps"):
        if k in sig: kw[k] = 10; break
    wav, _ = tts.synthesize(text, **kw)
    x = np.asarray(wav, dtype=np.float32).squeeze()
    i = np.where(np.abs(x) > 0.01)[0]
    return x[max(0, i[0] - int(.03 * SR)): i[-1] + int(.08 * SR)] if len(i) else x

sil = lambda s: np.zeros(int(SR * s), np.float32)
M = json.load(open("tools/ko_manifest.json"))
only = sys.argv[1] if len(sys.argv) > 1 else ""
for n, t in enumerate(M):
    if only and not t["path"].startswith(only): continue
    for ver, main, other in (("f", "F1", "M1"), ("m", "M1", "F1")):
        out = t["path"].replace("/X-", f"/{ver}-") + ".mp3"
        if os.path.exists(out): continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        a = [say(t["head"], main, t["speed"]), sil(1.0)]
        for s in t["segs"]:
            v = main if s["role"] == 0 else other
            for p in s["p"]:
                a.append(sil(p["pause"]) if isinstance(p, dict) else say(p, v, t["speed"]))
                if not isinstance(p, dict): a.append(sil(0.15))
            a.append(sil(s["after"]))
        sf.write("/tmp/x.wav", np.concatenate(a), SR)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "/tmp/x.wav", "-ac", "1", "-ar", "24000", "-b:a", "96k", out], check=True)
    print(n, t["path"], flush=True)
print("DONE")
