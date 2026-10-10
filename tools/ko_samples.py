"""Korean TTS candidates, run on GitHub Actions (internet access). Writes MP3s to samples/ko/."""
import asyncio, os, subprocess, traceback
OUT = "samples/ko"; os.makedirs(OUT, exist_ok=True)
TEXT = ("안녕하십니까. 오늘부로 해외사업팀에 발령받은 응우옌 탄입니다. 이렇게 함께 일하게 되어 기쁘게 생각합니다. "
        "팀장님, 잠시 시간 괜찮으십니까? 급히 보고드릴 일이 있습니다.")
log = []

async def edge():
    import edge_tts
    vs = [v for v in await edge_tts.list_voices() if v["Locale"] == "ko-KR"]
    log.append("edge ko-KR voices: " + ", ".join(v["ShortName"] for v in vs))
    for v in vs:
        n = v["ShortName"]
        await edge_tts.Communicate(TEXT, n).save(f"{OUT}/A_edge_{n}.mp3")

def supertonic():
    from supertonic import TTS
    import numpy as np, soundfile as sf
    tts = TTS()
    for name in ["F1", "F2", "F3", "M1", "M2", "M3"]:
        style = tts.get_voice_style(voice_name=name)
        wav, dur = tts.synthesize(TEXT, voice_style=style, lang="ko")
        wav = np.asarray(wav).squeeze()
        sr = getattr(tts, "sample_rate", 44100)
        sf.write(f"{OUT}/tmp.wav", wav, sr)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{OUT}/tmp.wav", "-b:a", "96k", f"{OUT}/B_supertonic_full_{name}.mp3"], check=True)
    os.remove(f"{OUT}/tmp.wav")

for name, fn in [("edge", lambda: asyncio.run(edge())), ("supertonic", supertonic)]:
    try: fn(); log.append(f"{name}: ok")
    except Exception: log.append(f"{name}: FAILED\n" + traceback.format_exc()[-1500:])
open(f"{OUT}/log.txt", "w").write("\n".join(log) + "\n")
print("\n".join(log))
