#!/usr/bin/env python3
"""Shadow & Shine Daily — player pages + state index (pure Python, no network).

Reads shadow/daily/dNNN/scripts.json and writes:
  shadow/daily/index.json             state: [{day, date, levels: {lv: {title, topic, genre}}}]
  shadow/daily/l{lv}/dNNN/index.html  player page (US/UK toggle, Normal / Repeat / Slow tracks)
  shadow/daily/index.html             list of all days
  index.html (root)                   adds/updates the "Shadow & Shine Daily" block between <!--daily--> markers
"""
import glob, html, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAILY = os.path.join(ROOT, "shadow", "daily")
LEVELS = {"1": "Sprout", "2": "Seedling", "3": "Sapling", "4": "Tree"}
FOOT = "© 2026 EnL_language. All rights reserved. For personal and classroom use only. Do not copy, share, or redistribute without permission."

# same look as the book player pages (shadow/l1/w01/index.html)
HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · E&amp;L Audio</title><meta name="robots" content="noindex"><style>
:root{{--bg:#FBF8F2;--card:#fff;--ink:#22252B;--mut:#6B6F78;--line:#E6E1D6;--acc:#2F5D8A;--chip:#EEF2F7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181C;--card:#1F2228;--ink:#ECEDEF;--mut:#A3A7AF;--line:#30343B;--acc:#8DB4E0;--chip:#262B33}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif}}
.wrap{{max-width:640px;margin:0 auto;padding:20px 16px 40px}}
.brand{{display:flex;align-items:center;gap:8px;font-weight:700;color:var(--acc);font-size:14px;letter-spacing:.02em}}
.brand a{{color:inherit;text-decoration:none}}
h1{{font-size:24px;line-height:1.25;margin:14px 0 4px}}.sub{{color:var(--mut);margin:0 0 18px;font-size:14px}}
.tabs{{display:flex;gap:8px;margin:0 0 14px}}.tabs button{{flex:1;padding:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;font:600 15px inherit;cursor:pointer}}
.tabs button[aria-selected=true]{{background:var(--acc);border-color:var(--acc);color:#fff}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 14px 12px;margin:0 0 12px}}
.card h2{{font-size:16px;margin:0 0 2px}}.card p{{margin:0 0 10px;color:var(--mut);font-size:13px}}
audio{{width:100%}}.text{{white-space:pre-line;background:var(--chip);border-radius:12px;padding:14px;font-size:17px;line-height:1.8}}
.list a{{display:block;padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin:0 0 8px;background:var(--card);color:var(--ink);text-decoration:none}}
.list a span{{color:var(--mut);font-size:13px;margin-left:6px}}
h3{{font-size:15px;margin:22px 0 8px;color:var(--acc)}}
footer{{margin-top:28px;font-size:11px;color:var(--mut);border-top:1px solid var(--line);padding-top:12px}}
</style></head><body><div class="wrap">
"""
TAIL = '<footer>' + html.escape(FOOT) + '</footer></div>{script}</body></html>\n'
TOGGLE_JS = """<script>
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.tabs button').forEach(x=>x.setAttribute('aria-selected',x===b));
 document.querySelectorAll('[data-acc]').forEach(s=>s.hidden=s.dataset.acc!==b.dataset.acc);
 document.querySelectorAll('audio').forEach(a=>a.pause());
 try{localStorage.setItem('acc',b.dataset.acc)}catch(e){}
});
try{const a=localStorage.getItem('acc');if(a){const b=document.querySelector('.tabs button[data-acc="'+a+'"]');b&&b.click()}}catch(e){}
</script>"""

e = html.escape


def plain(line):
    t = line.replace("*", "").replace("↗", "").replace("↘", "")
    return re.sub(r"\s*\|\s*", " / ", t).strip()


def tracks(acc):
    c = lambda h, p, f: f'<div class="card"><h2>{h}</h2><p>{p}</p><audio controls preload="none" src="{f}"></audio></div>'
    return (c("Track 1 · Listen &amp; Shadow", "Listen 3 times, then speak WITH the audio.", f"{acc}-1.mp3")
            + c("Track 2 · Repeat", "Say each part in the pause, then the whole line.", f"{acc}-2.mp3")
            + c("Slow · Listen", "Slow speed for the first listen or for dictation.", f"{acc}-slow.mp3"))


def player(day, date, lv, sc):
    t = f"Day {day} · {sc['title']}"
    body = (f'<div class="brand"><a href="../../">📖 E&amp;Languages Audio</a></div><h1>{e(t)}</h1>'
            f'<p class="sub">Shadow &amp; Shine Daily · Level {lv} {LEVELS[lv]} · {e(sc["title_kr"])} · {e(date)}</p>'
            '<div class="tabs" role="tablist"><button data-acc="US" aria-selected="true">🇺🇸 American</button>'
            '<button data-acc="UK" aria-selected="false">🇬🇧 British</button></div>'
            f'<section data-acc="US">{tracks("us")}</section><section data-acc="UK" hidden>{tracks("uk")}</section>'
            '<h3>My Shadow Text</h3><div class="text">' + e("\n".join(plain(l) for l in sc["lines"])) + '</div>\n')
    return HEAD.format(title=e(t)) + body + TAIL.format(script=TOGGLE_JS)


def main():
    days = []
    for sp in sorted(glob.glob(os.path.join(DAILY, "d[0-9][0-9][0-9]", "scripts.json"))):
        d = json.load(open(sp, encoding="utf-8"))
        days.append(d)
        nnn = "d%03d" % d["day"]
        for lv, sc in d["scripts"].items():
            out = os.path.join(DAILY, "l" + lv, nnn)
            os.makedirs(out, exist_ok=True)
            open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(player(d["day"], d["date"], lv, sc))
    days.sort(key=lambda d: d["day"])
    state = [{"day": d["day"], "date": d["date"],
              "levels": {lv: {"title": sc["title"], "topic": sc.get("topic", ""), "genre": sc["genre"]} for lv, sc in sorted(d["scripts"].items())}}
             for d in days]
    json.dump(state, open(os.path.join(DAILY, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    items = ""
    for d in reversed(days):
        nnn = "d%03d" % d["day"]
        items += f'<h3>Day {d["day"]} · {e(d["date"])}</h3><div class="list">' + "".join(
            f'<a href="l{lv}/{nnn}/">Level {lv} · {LEVELS[lv]} — {e(sc["title"])}<span>{e(sc["title_kr"])}</span></a>'
            for lv, sc in sorted(d["scripts"].items())) + '</div>'
    page = (HEAD.format(title="Shadow &amp; Shine Daily") + '<div class="brand"><a href="../../">📖 E&amp;Languages Audio</a></div>'
            f'<h1>Shadow &amp; Shine Daily</h1><p class="sub">A new text every day for each level · {len(days)} day(s) · American &amp; British audio</p>'
            + items + "\n" + TAIL.format(script=""))
    open(os.path.join(DAILY, "index.html"), "w", encoding="utf-8").write(page)

    root = os.path.join(ROOT, "index.html")
    s = open(root, encoding="utf-8").read()
    block = (f'<!--daily--><h3>Shadow &amp; Shine Daily</h3><div class="list"><a href="shadow/daily/">Daily texts · all levels'
             f'<span>{len(days)} day(s) · latest Day {days[-1]["day"]}</span></a></div><!--/daily-->') if days else ""
    if "<!--daily-->" in s:
        s = re.sub(r"<!--daily-->.*?<!--/daily-->", block, s, flags=re.S)
    else:
        anchor = '<h3>Speak Up!'
        s = s.replace(anchor, block + anchor, 1)
    open(root, "w", encoding="utf-8").write(s)
    print(f"pages for {len(days)} day(s)")


if __name__ == "__main__":
    main()
