#!/usr/bin/env python3
"""Shadow & Shine Daily — A4 worksheet PDFs (one per level per day).

Usage: python tools/daily/build_worksheets.py DAY [OUT_DIR]
Each PDF: 1) Shadowing worksheet  2) Dictation worksheet  3) Answer key & teacher script.
HTML → PDF with Chromium (Playwright). Needs: pip install segno playwright; font "Noto Sans CJK KR".
"""
import html, json, os, re, sys

import segno
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "https://ellie0209.github.io/enl-audio/shadow/daily/"
FOOTER = "© 2026 Ellie. For classroom use only. No part of this material may be copied or distributed without permission."
# from e-languages lib/shadowing/content.json "levels" (script font: level size, never below 12pt)
LEVELS = {
    "1": dict(name="Sprout", ar="AR 0.5 – 1.4", grades="K (6세) – Grade 1", color="#4E9F57", light="#E8F4E9", font=22),
    "2": dict(name="Seedling", ar="AR 1.5 – 2.4", grades="Grade 1 – 2", color="#2A8C82", light="#E3F2F0", font=17),
    "3": dict(name="Sapling", ar="AR 2.5 – 3.4", grades="Grade 2 – 3", color="#D9822B", light="#FBEEDF", font=13.5),
    "4": dict(name="Tree", ar="AR 3.5 – 4.5+", grades="Grade 3", color="#5B4FC4", light="#ECEAF9", font=12),
}
e = html.escape


def qr(url):
    return segno.make(url, error="m").svg_data_uri(scale=4, border=1, dark="#22252B")


def script_html(line, stress=True, num=None):
    out = []
    parts = line.replace(" ↗", "\u00a0↗").replace(" ↘", "\u00a0↘").split(" | ")
    for i, p in enumerate(parts):
        for t in re.split(r"(\*[^*]+\*)", p):
            if t.startswith("*") and t.endswith("*") and len(t) > 2:
                out.append(f"<b>{e(t[1:-1])}</b>" if stress else e(t[1:-1]))
            else:
                t = e(t).replace("↗", '<span class="arw">↗</span>').replace("↘", '<span class="arw">↘</span>')
                out.append(t)
        if i < len(parts) - 1:
            out.append('<span class="bar">/</span>')
    n = f'<span class="num">{num}</span>' if num else ""
    return f"<p>{n}{''.join(out)}</p>"


def stressed(line):
    return [m.group(1) for m in re.finditer(r"\*([^*]+)\*", line)]


def pick_blanks(line, targets):
    """At most 2 stressed groups per line; groups containing a target word first, then in reading order."""
    groups = stressed(line)
    tset = {t.lower() for t in targets}
    has_t = lambda g: any(w.lower().strip("!?.,") in tset for w in g.split())
    order = sorted(range(len(groups)), key=lambda i: (not has_t(groups[i]), i))[:2]
    return set(order)


def blank_line(line, targets, answer=False):
    keep = pick_blanks(line, targets)
    idx = [-1]

    def rep(m):
        idx[0] += 1
        w = m.group(1)
        if idx[0] in keep:
            width = max(3.2, len(w) * 0.62 + 1.4)
            if answer:
                return f'<span class="ans">{e(w)}</span>'
            return f'<span class="blank" style="width:{width:.1f}em"></span>'
        return e(w)

    t = re.sub(r"\*([^*]+)\*", rep, line.replace("↗", "").replace("↘", ""))
    return re.sub(r"\s*\|\s*", " ", t).strip()


def plain(line):
    return re.sub(r"\s*\|\s*", " ", line.replace("*", "").replace("↗", "").replace("↘", "")).strip()


def dictation_lines(lines, n):
    cand = []
    for i, l in enumerate(lines):
        p = plain(l)
        words = len(p.split())
        if words < 3 or words > 12:
            continue
        cand.append(((("“" in p) or ("—" in p)), len(p), i))
    cand.sort()
    return sorted(i for _, _, i in cand[:n])


def hw_lines(n=1, hint=""):
    h = f'<span class="hint">{e(hint)}</span>' if hint else ""
    return "".join(f'<div class="hw">{h if k == 0 else ""}</div>' for k in range(n))


SOLO = {
    "1": ("Solo · 혼자 읽기", "Read the target words by yourself. Tick each word you can read. · 목표 단어를 혼자 읽고, 읽은 단어에 ✓ 해요."),
    "2": ("Solo · 다시 말하기", "Retell the story without looking: Beginning → Middle → End. · 글을 보지 않고 처음–중간–끝으로 다시 말해요."),
    "3": ("Solo · 스피치", "Say the text like a speech with accurate sounds, pauses and strong words. · 정확한 발음·쉼·강세로 스피치해요."),
    "4": ("Solo · 전체 리텔링", "Retell the whole text from memory with all the details, then record it. · 기억해서 모든 내용을 다시 말하고 녹음해요."),
}


def solo_box(lv, sc):
    h, p = SOLO[lv]
    if lv == "1":
        body = '<div class="chips">' + "".join(f'<span class="chip"><i class="cb"></i>{e(w)}</span>' for w in sc["targets"]) + "</div>"
    elif lv == "2":
        body = '<div class="bme">' + "".join(
            f'<div><b>{a}</b><small>{b}</small><div class="hwline"></div></div>'
            for a, b in [("Beginning · 처음", "First, …"), ("Middle · 중간", "Then, …"), ("End · 끝", "At the end, …")]) + "</div>"
    elif lv == "3":
        items = ["I paused at every / mark. · / 에서 쉬었어요", "I said the bold words strongly. · 굵은 단어를 강하게 말했어요",
                 "My voice went up ↗ and down ↘. · 억양을 살렸어요", "Tricky words: " + ", ".join(sc["practice"])]
        body = '<ul class="ticks">' + "".join(f"<li><i class='cb'></i>{e(t)}</li>" for t in items) + "</ul>"
    else:
        n = len(sc["events"]) or 8
        body = (f'<p class="small">How many events did you remember? · 기억한 사건 수에 색칠해요 (teacher has the list)</p><div class="evn">'
                + "".join(f"<span>{k}</span>" for k in range(1, n + 1)) + "</div>")
    return f'<section class="box"><h3>{h}</h3><p class="small">{p}</p>{body}</section>'


def header(lv, day, date, sc, kind, qrs, note=""):
    L = LEVELS[lv]
    q = "".join(f'<figure><img src="{qr(u)}"><figcaption>{e(c)}</figcaption></figure>' for c, u in qrs)
    return f"""<header class="hd"><div class="band"><span>Shadow &amp; Shine Daily · Level {lv} {L['name']} · {L['ar']}</span><span class="nm">Name ________________</span></div>
<div class="hrow"><div><p class="kind">{kind} · Day {day} · {e(date)}</p><h1>{e(sc['title'])}</h1><p class="kr">{e(sc['title_kr'])} · {e(sc['genre'])}</p>{note}
</div><div class="qrs">{q}</div></div></header>"""


def page_shadow(lv, day, date, sc, urls):
    L = LEVELS[lv]
    lines = "".join(script_html(l, True, (i + 1) if lv != "1" else None) for i, l in enumerate(sc["lines"]))
    vocab = "".join(f"<tr><td><b>{e(a)}</b></td><td>{e(b)}</td></tr>" for a, b in sc["vocab"])
    sounds = "".join(f'<li><b>{e(a)}</b> <i>{e(b)}</i><br><span>{e(c)}</span></li>' for a, b, c in sc["sounds"])
    steps = [("1 Listen ×2", "듣기"), ("2 Repeat", "따라"), ("3 Shadow", "동시에"), ("4 Solo", "혼자")]
    check = "".join(f'<span class="step"><i class="cb"></i><b>{a}</b> <small>{b}</small></span>' for a, b in steps)
    return f"""<div class="sheet">{header(lv, day, date, sc, 'Shadowing Worksheet', [('PLAYER', urls['page']), ('AUDIO', urls['us1'])])}
<section class="script" style="font-size:{L['font']}pt">{lines}
<p class="key"><span class="bar">/</span> pause · 쉬기 &nbsp; <b>bold</b> = say it strong · 강하게 &nbsp; ↗ up · ↘ down</p></section>
<div class="two"><section class="box"><h3>Words · 단어</h3><table class="vocab">{vocab}</table></section>
<section class="box"><h3>Sound Tips · 소리 포인트</h3><ul class="sounds">{sounds}</ul>
<p class="pro"><b>Read Like a Pro · 표현 팁</b><br>{e(sc['expression'])}</p></section></div>
{solo_box(lv, sc)}
<section class="box"><div class="steps"><b class="lbl">Steps ✓</b>{check}</div><div class="steprow">
</div><div class="starline"><span><em>☆</em> 4 steps · 집 연습</span><span><em>☆</em> Solo · 혼자</span><span><em>☆</em> Teacher · 선생님</span>
<span class="sign">Parent / Teacher sign · 확인 ________________</span></div></section></div>"""


def page_dictation(lv, day, date, sc, urls, answer=False):
    tg = sc["targets"]
    if answer:
        a = '<div class="tw ans-grid">' + "".join(f'<span class="ans">{k + 1}. {e(w)}</span>' for k, w in enumerate(tg)) + "</div>"
    else:
        a = '<div class="tw">' + "".join(
            f'<div class="twi"><span class="n">{k + 1}</span>{hw_lines(1, w[0] if len(w) > 2 else "")}</div>' for k, w in enumerate(tg)) + "</div>"
    b = "<ol class='bl'>" + "".join(f"<li>{blank_line(l, tg, answer)}</li>" for l in sc["lines"]) + "</ol>"
    n = 2 if lv in ("1", "2") else 3
    sel = dictation_lines(sc["lines"], n)
    if answer:
        c = "<ol class='cl'>" + "".join(f'<li><span class="ans">{e(plain(sc["lines"][i]))}</span> <small>(line {i + 1})</small></li>' for i in sel) + "</ol>"
    else:
        c = "<ol class='cl'>" + "".join(f"<li>{hw_lines(2)}</li>" for _ in sel) + "</ol>"
    if answer:
        return f"""<h2 class="sec">Dictation · Answer Key</h2>
<section class="box"><h3>A. Target Words</h3>{a}</section>
<section class="box"><h3>B. Fill in the Blanks</h3>{b}</section>
<section class="box"><h3>C. Sentence Dictation</h3>{c}</section>"""
    bar = "".join(f'<span><i class="cb"></i>{t}</span>' for t in ["Shadowing done first?", "Capital", "Spaces", "Period"])
    return f"""<div class="sheet">{header(lv, day, date, sc, 'Dictation Worksheet', [('SLOW', urls['slow']), ('NORMAL', urls['us1'])], '<p class="inst">Shadow first → SLOW → check with NORMAL</p>')}
<section class="box"><h3>A. Target Words · 목표 단어 <small>Listen and write. The first letter is a hint. · 첫 글자가 힌트예요.</small></h3>{a}</section>
<section class="box"><h3>B. Listen and Fill in · 빈칸 채우기 <small>Write the strong words. · 강하게 들리는 단어를 써요.</small></h3>{b}</section>
<section class="box brk"><h3>C. Write the Whole Sentence · 문장 받아쓰기</h3>{c}<div class="checkbar">{bar}<span class="sign">Parent / Teacher · 확인 ____________ &nbsp; Score ____ / {len(tg) + sum(len(pick_blanks(l, tg)) for l in sc['lines']) + n}</span></div></section></div>"""


def page_teacher(lv, day, date, sc, urls):
    L = LEVELS[lv]
    lines = "".join(script_html(l, True, i + 1) for i, l in enumerate(sc["lines"]))
    words = sum(len(plain(l).split()) for l in sc["lines"])
    ev = ""
    if sc.get("events"):
        ev = '<section class="box"><h3>Retell Event Checklist · 사건 목록</h3><ol class="ev">' + "".join(f"<li>{e(x)}</li>" for x in sc["events"]) + "</ol></section>"
    plan = [("1 Listen", "Play Normal (or Slow) twice. Students only listen; no text the first time.", "듣기만 2번"),
            ("2 Repeat", "Play the Repeat track. Students say each phrase in the pause, then the whole line.", "멈출 때 따라 말하기"),
            ("3 Shadow", "Play Normal again. Students speak at the same time, following the / and bold words.", "동시에 말하기"),
            ("4 Solo", SOLO[lv][1].split(" · ")[0], "혼자 말하기 · 녹음")]
    planh = "".join(f"<tr><td><b>{a}</b></td><td>{e(b)}</td><td>{c}</td></tr>" for a, b, c in plan)
    return f"""<div class="sheet"><header class="hd"><div class="band">Answer Key &amp; Teacher Script · Level {lv} {L['name']} · Day {day} · {e(date)}</div>
<div class="hrow"><div><p class="kind">For teachers · 교사용</p><h1>{e(sc['title'])}</h1><p class="kr">{e(sc['title_kr'])} · {e(sc['genre'])} · {words} words · {len(sc['lines'])} lines</p></div>
<div class="qrs"><figure><img src="{qr(urls['page'])}"><figcaption>PLAYER</figcaption></figure></div></div></header>
<section class="box"><h3>Teacher Script · 지문 (stress / phrase / intonation)</h3><div class="script tscript">{lines}</div></section>
<section class="box"><h3>10-minute Lesson · 수업 흐름</h3><table class="plan">{planh}</table>
<p class="small"><b>Expression:</b> {e(sc['expression'])} &nbsp; <b>Practice:</b> {e(' · '.join(sc['practice']))}</p></section>
{page_dictation(lv, day, date, sc, urls, answer=True)}{ev}</div>"""


CSS = """
@page{size:A4;margin:10mm 12mm 12mm 12mm}
*{box-sizing:border-box}
body{margin:0;font-family:"Noto Sans CJK KR","Noto Sans KR","DejaVu Sans",sans-serif;font-size:12pt;color:#22252B;line-height:1.4}
.sheet{break-after:page}.sheet:last-child{break-after:auto}
.hd{border:2px solid var(--lv);border-radius:10px;overflow:hidden;margin-bottom:8px;break-inside:avoid}
.band{background:var(--lv);color:#fff;font-weight:700;font-size:12pt;padding:4px 12px;display:flex;justify-content:space-between}.band .nm{font-weight:400}
.hrow{display:flex;justify-content:space-between;align-items:center;padding:3px 12px;background:var(--lt)}
.kind{margin:0;font-size:12pt;font-weight:700;color:var(--lv)}
h1{margin:0;font-size:19pt;line-height:1.1}.kr{margin:1px 0 0;font-size:12pt;color:#555}
.name{margin:3px 0 0;font-size:12pt;color:#444}
.qrs{display:flex;gap:8px}.qrs figure{margin:0;text-align:center}.qrs img{width:17mm;height:17mm;display:block;background:#fff}
.qrs figcaption{font-size:12pt;line-height:1.1;font-weight:700;color:var(--lv)}
.script{background:var(--lt);border:1.5px solid var(--lv);border-radius:10px;padding:5px 10px;margin-bottom:6px;font-family:"DejaVu Serif","Noto Serif CJK KR",serif;line-height:1.38}
.script p{margin:0 0 3px}.script p:has(.num){padding-left:1.3em;text-indent:-1.3em}.script b{color:#111;font-weight:800}
.bar{color:var(--lv);font-weight:700;margin:0 .3em}.arw{color:var(--lv);font-weight:700}
.num{display:inline-block;text-indent:0;min-width:1.7em;color:#888;font-family:"DejaVu Sans",sans-serif;font-size:.75em}
.key{font-family:"Noto Sans CJK KR",sans-serif;font-size:12pt !important;color:#555;margin:2px 0 0 !important}
.tscript{font-size:13pt}
.box{border:1.5px solid #D9D4C7;border-radius:10px;padding:4px 12px 6px;margin-bottom:6px;break-inside:avoid}
.box h3{margin:0 0 2px;font-size:13pt;color:var(--lv)}.box h3 small{font-weight:400;color:#666;font-size:12pt}
.small{font-size:12pt;color:#555;margin:2px 0 4px}
.steps{display:flex;gap:8px}.step{white-space:nowrap}
.cb{display:inline-block;width:13px;height:13px;border:1.6px solid var(--lv);border-radius:3px;margin-right:5px;vertical-align:-1px;flex:none}
.two{display:grid;grid-template-columns:minmax(0,max-content) 1fr;gap:8px}.two .box{margin-bottom:6px}
.vocab{border-collapse:collapse;width:100%}.vocab td{white-space:nowrap;padding:1px 4px;border-bottom:1px dotted #ccc;font-size:12pt;vertical-align:top}
.sounds{margin:0;padding-left:16px}.sounds li{margin-bottom:1px;font-size:12pt;line-height:1.25}.sounds i{color:#555}.sounds span{color:#333}
.pro{margin:4px 0 0;font-size:12pt;border-top:1px dashed #ccc;padding-top:3px}.pro b{color:var(--lv)}
.pair{display:grid;grid-template-columns:1.45fr 1fr;gap:8px;align-items:stretch}.pair .box{margin-bottom:6px}
.steps{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:12pt}.steps .lbl{color:var(--lv)}.steps small{color:#666;font-size:12pt}
.starline{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px;margin-top:4px;font-size:12pt}.starline .sign{margin:0 0 0 auto}.starline em{font-style:normal;font-size:18pt;color:var(--lv);vertical-align:-2px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1.5px solid var(--lv);border-radius:999px;padding:1px 10px;font-size:15pt;font-weight:700;display:inline-flex;align-items:center}
.bme{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}.bme b{display:block;color:var(--lv)}.bme small{color:#777;font-size:12pt}
.hwline{border-bottom:1px solid #999;height:9mm}
.ticks{list-style:none;margin:0;padding:0}.ticks li{margin:1px 0;font-size:12pt}
.evn{display:flex;flex-wrap:wrap;gap:6px}.evn span{width:11mm;height:11mm;border:1.6px solid var(--lv);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--lv)}
.starrow{display:flex;justify-content:space-around;margin-top:4px}.starrow span{font-size:24pt;color:var(--lv);text-align:center;line-height:1}
.starrow small{display:block;font-size:12pt;color:#555}
.sign{margin:6px 0 0;font-size:12pt}
.inst{margin:2px 0 0;font-size:12pt;color:#444}
.tw{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px}
.twi{display:flex;align-items:flex-end;gap:6px}.twi .n{font-weight:700;color:var(--lv);width:1.4em}
.hw{flex:1;height:9.5mm;position:relative;border-top:1px solid #9a9a9a;border-bottom:1.4px solid #555;
 background:linear-gradient(to bottom,transparent calc(50% - .5px),#bbb calc(50% - .5px),#bbb calc(50% + .5px),transparent calc(50% + .5px));
 background-size:100% 100%;margin-top:3px}
.hw::after{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px dashed #fff}
.hint{position:absolute;left:4px;bottom:0;font-size:19pt;line-height:1;color:#B0B0B0;font-family:"DejaVu Sans",sans-serif}
.bl{margin:0;padding-left:22px}.bl li{font-size:12.5pt;line-height:1.8}
.blank{display:inline-block;border-bottom:1.5px solid #333;height:1.1em;vertical-align:-2px;margin:0 2px}
.cl{margin:0;padding-left:22px}.cl .hw{height:9mm}.cl li{margin-bottom:4px;break-inside:avoid}.checkbar{break-inside:avoid}
.checkbar .sign{margin:0 0 0 auto}.checkbar{border-top:1px dashed #ccc;padding-top:4px;margin-top:4px;display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12pt}
.ans{color:#B23B3B;font-weight:700;border-bottom:1.5px solid #B23B3B;padding:0 2px}
.ans-grid{grid-template-columns:repeat(3,1fr)}.ans-grid .ans{border:0}
.sec{font-size:16pt;color:var(--lv);margin:0 0 6px;break-before:page}
.plan{border-collapse:collapse;width:100%}.plan td{border-bottom:1px dotted #ccc;padding:3px 4px;font-size:12pt;vertical-align:top}
.brk{break-inside:auto}.brk h3{break-after:avoid}
.ev{margin:0;padding-left:22px;font-size:12pt}
"""


def build(day, out_dir):
    nnn = "d%03d" % day
    d = json.load(open(os.path.join(ROOT, "shadow/daily", nnn, "scripts.json"), encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        for lv, sc in sorted(d["scripts"].items()):
            L = LEVELS[lv]
            b = f"{BASE}l{lv}/{nnn}/"
            urls = dict(page=b, us1=b + "us-1.mp3", slow=b + "us-slow.mp3")
            doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head>'
                   f'<body style="--lv:{L["color"]};--lt:{L["light"]}">'
                   + page_shadow(lv, d["day"], d["date"], sc, urls) + page_dictation(lv, d["day"], d["date"], sc, urls)
                   + page_teacher(lv, d["day"], d["date"], sc, urls) + "</body></html>")
            open(os.path.join(out_dir, f"L{lv}.html"), "w", encoding="utf-8").write(doc)
            pg.set_content(doc, wait_until="load")
            fn = os.path.join(out_dir, f"ShadowShine_Daily_D{day:03d}_L{lv}_{L['name']}.pdf")
            foot = ('<div style="width:100%;font-family:\'Noto Sans CJK KR\',sans-serif;font-size:8pt;color:#666;text-align:center;'
                    f'padding:0 13mm">{e(FOOTER)}</div>')
            pg.pdf(path=fn, format="A4", print_background=True, display_header_footer=True,
                   header_template="<div></div>", footer_template=foot,
                   margin=dict(top="10mm", bottom="12mm", left="12mm", right="12mm"))
            paths.append(fn)
        br.close()
    for f in paths:
        print(f)


if __name__ == "__main__":
    build(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "out"))
