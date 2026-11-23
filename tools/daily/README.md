# Shadow & Shine Daily — publication tools

One new original text per level (1 Sprout, 2 Seedling, 3 Sapling, 4 Tree) is intended each day. **The external content job still writes the new texts.** Nothing in this repository authors a new passage or guarantees that an external scheduler is enabled.

## Publication contract

1. The content job writes `shadow/daily/dNNN/scripts.json` and pushes it to main. It must supply exactly four levels and a unique `YYYY-MM-DD` date in Asia/Seoul. Day numbers are sequence numbers, not calendar offsets: the historical catalog skips November 10.
2. `.github/workflows/shadow-daily.yml` checks out the latest main, validates inputs, creates US/UK Normal/Slow/Repeat MP3s and worksheet PDFs, and validates the complete output before updating the catalog.
3. The publisher copies only generated assets onto a fresh checkout of main, regenerates the catalog/player pages there, and commits them together. It never changes scripts, force-pushes, or rebases binary files. A concurrent unrelated commit is preserved and publication is retried at most three times. If any Daily inputs or build tools changed, old outputs are discarded and the run fails with a rebuild instruction; the new source push will trigger the next run.
4. After saving, the workflow explicitly requests a build of the existing branch-based GitHub Pages site and verifies the public catalog, scripts, and all 28 assets of the latest registered date. The Pages source/settings and public address are not changed. A deployment/API/CDN failure remains a failed publication run even when the repository commit succeeded.

Do **not** push a newly generated catalog ahead of the assets. `build_pages.py` now filters out days without current audio and worksheet source stamps; `--strict` fails if any registered day is incomplete. If no days are ready, a standalone non-strict run leaves the existing catalog intact instead of erasing it. The production publisher always builds and validates all registered days before writing a strict catalog.

## Files

| Path | Purpose |
|---|---|
| `shadow/daily/dNNN/scripts.json` | Four original scripts, date and sequence number |
| `shadow/daily/index.json` | Published catalog consumed by the app |
| `shadow/daily/l{lv}/dNNN/` | Six MP3s, player page, worksheet PDF and source stamps |
| `.lines.sha1` in each level/day | Current voice/speed/text signature; compatible with existing MP3 caches |
| `.worksheet.sha256` in each level/day | Signature of the full level content, date and PDF template |
| `ShadowShine_Daily_DNNN_L{lv}_{Level}.pdf` | Shadowing, dictation and teacher/answer sections |
| `shadow/app/` | Retired public app (2026-11-22); notice page links to the E&Languages member app at https://e-languages.vercel.app/shadow-daily. Its service worker unregisters itself and deletes its caches. |

The first production run after this change renders all registered level PDFs to establish worksheet stamps (currently 22 days × 4 levels = 88 PDFs). Existing PDF paths and names are retained, but the files are regenerated; byte-for-byte preservation is not guaranteed. Existing audio is reused when its current signature and six files are present. Later runs render only missing/changed worksheet days. A metadata/teacher-tip change invalidates the PDF even when the spoken lines are unchanged. The `force` input rebuilds all existing audio and PDFs; it does not create a new day.

## Member app and retired public app

Shadow & Shine Daily now runs in the E&Languages member app at https://e-languages.vercel.app/shadow-daily (`e-languages/app/shadow-daily/route.js`). It reads the same `index.json`, `scripts.json`, MP3s and PDFs from this repository. Preserve the retired public app notice and self-unregistering service worker; this publication update does not restore the old public PWA or change member-app progress.

## Tools and local use

- `publication.py`: shared four-level/date validation, source signatures, file checks, MP3 format/duration checks via ffprobe, and PDF parsing/nonempty-page checks via pypdf.
- `build_audio.py`: Kokoro TTS with fixed voices and speeds, preserving the existing audio cache format.
- `build_worksheets.py --all`: builds pending PDFs using Playwright/Chromium, waits for fonts, validates PDFs before installing them in the public directories, and writes worksheet stamps. `DAY OUT_DIR` remains available for a local PDF preview without publication.
- `build_pages.py [--strict]`: readiness-gated catalog and player generation.
- `publish_daily.py [--force]`: full generation/validation and bounded publication retries. This command **pushes to main**, so run only with publication authorization and a clean committed checkout of the Daily source files.
- `check_daily.py`: read-only diagnostics and public byte comparison; no generation, push, paid API call, or automatic repair.

For full publication, install Python 3.11, ffmpeg, espeak-ng, Noto CJK/DejaVu fonts, CPU PyTorch, `requirements-build.txt`, and `python -m playwright install --with-deps chromium`. The workflow has the exact installation steps. PDF rendering increases runner time; the setup uses no paid content-generation API.

## Daily missing-publication check

`.github/workflows/shadow-daily-check.yml` runs at **23:50 Asia/Seoul** (`50 14 * * *` UTC). GitHub can delay scheduled runs; the checker selects the most recent scheduled deadline even if a run begins after KST midnight. The date is matched directly, rather than inferred from the day number.

| Result | Meaning / next action |
|---|---|
| `source_missing` | No scripts for the expected date; inspect the external content job and its schedule/logs |
| `input_invalid` | Incorrect date/schema/level set; fix the source before rebuilding |
| `asset_incomplete` | MP3/PDF missing or source stamp outdated; inspect the publication job |
| `catalog_incomplete` | Assets exist but the current catalog does not include them |
| `public_stale` | Public scripts/catalog do not match main; inspect Pages deployment/CDN |
| `public_asset_unavailable` | A public MP3/PDF cannot be retrieved |
| `public_asset_mismatch` | Public asset bytes differ from the expected release |
| `ok` | Catalog, scripts, 24 MP3s and four PDFs match the expected release |

The check exits nonzero on any failure and writes its result in the Actions run summary. This creates a visible failed check; notification delivery depends on the user's GitHub notification settings. It does not send messages or silently recreate missing content. The post-publication check waits up to 10 minutes for Pages/CDN propagation; the nightly check reports immediately.

The external text generator's provider, schedule, credentials and logs were not found in this repository. Confirm those independently before claiming end-to-end daily generation is enabled. A `schedule` on the audio/PDF builder alone cannot supply missing texts. The e-languages homepage is not updated by this pipeline (PR #17 was closed by request).

## Tests

`python -m unittest discover -s tests/daily -v` covers incomplete/new days, changed text/metadata, local/public failure classification, asset byte mismatches, delayed checks across KST midnight, real local Git concurrent-writer retries, stale-source rejection, commit-error propagation and idempotent publication. The Git tests push only to temporary local bare repositories.

The PR-only `.github/workflows/shadow-daily-tests.yml` also renders Day 20 in four levels on a runner with Chromium and Korean fonts, checks PDF pages/text, and never calls TTS, commits, or deploys. Production generation and nightly checks run only after their workflow files reach main; PR creation does not run the production publisher.

## Voices (unchanged)

- US: Kokoro `af_heart` (lang `a`); UK: `bf_emma` (lang `b`).
- Model `hexgrad/Kokoro-82M`; 24 kHz mono MP3, 96 kbps.
- Normal speed L1/L2/L3/L4: 0.72/0.75/0.75/0.80; line gaps 1.5/1.3/1.2/0.8 seconds.
- Slow: normal ×0.8; gap ×1.4. Echo pauses: phrase length ×1.2 +0.8 seconds; line length ×1.1 +1.2 seconds.

© 2026 Ellie. For classroom use only. No part of this material may be copied or distributed without permission.
