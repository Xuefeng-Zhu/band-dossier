# Verify Dossier

The fresh Band run used the same three seat mandates as the verified build on `main`. It reached Stage 4 acceptance in 122.1 minutes from its sole human dispatch. The verified baseline took 117.1 minutes on the same clock. This branch preserves the four exact stage trees and their Git history. The included `room.json` belongs to the baseline. [Fresh Band room](https://app.band.ai/rooms/56bc7b26-1280-4cbd-ab75-36492a7d432c) · [Baseline factory](../FACTORY.md)

| Folder | Accepted commit | Cumulative organizer checks | USD currency cases | Chromium captures | Independent checks |
| --- | --- | ---: | ---: | ---: | ---: |
| `stage-1/` | `0a37dc6d05930426f338d0c791a7e8d5cca3727f` | 122/122 | 13/13 | — | 241/241 |
| `stage-2/` | `cd99825a523b2608bd34237459a208794f2c5351` | 134/134 | 13/13 | 12/12 | 154/154 |
| `stage-3/` | `b445f350a8a5554fdfb91562b28dfdb475753e61` | 143/143 | 13/13 | 12/12 | 353/353 |
| `stage-4/` | `c90b2c33d1b3b925c4d913a388bdb53fb17cd280` | 153/153 | 13/13 | 12/12 | 507/507 |

The Reviewer checked each accepted revision in isolation. Stage 1 required a correction to retain a valid USD expression. The organizer checks used Docker and mock providers. Chromium covered six routes at 375 px and 1440 px. Both runs passed the same organizer, currency and Chromium totals. The independent assertion counts come from different suites. [Participant guide](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#build-and-check-each-stage)

## Reproduce the organizer checks

Run this from a directory without existing `band-dossier/` or `sf-buildathon-2026/` checkouts. Use Python 3.12 or later and a running Docker daemon.

```bash
git clone --branch codex/dossier-band-c90b2c3 https://github.com/Xuefeng-Zhu/band-dossier.git
git clone https://github.com/band-ai/sf-buildathon-2026.git
cd sf-buildathon-2026
git checkout --detach 704324580f8ac1f893dc2e0a0339b9b3905e7707
python3.12 -m venv .venv
.venv/bin/python -m pip install -r harness/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m harness check ../band-dossier --track dossier
.venv/bin/python -m harness run --track dossier --repo ../band-dossier --all --mode isolated
```

For rootless Docker on Linux, set `DOCKER_HOST` to your daemon socket before running the harness. Look for the final `claims stage 1` through `claims stage 4` summary. A failing probe for the next stage is expected for Stages 1–3 because each folder contains the implementation for its own stage. Isolated mode uses the organizer’s mock providers. [Participant guide](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#before-you-submit)

For a manual startup check, follow the `RUN.md` in each of [Stage 1](../stage-1/RUN.md), [Stage 2](../stage-2/RUN.md), [Stage 3](../stage-3/RUN.md) and [Stage 4](../stage-4/RUN.md). Check `/health`, and open the UI for Stages 2–4.

## Comparison with the verified build

| Check | Verified build | Fresh Band build |
| --- | --- | --- |
| Stage 1 discovery fixtures | 0/2, 102 mock units | 1/2, 142 mock units |
| Stage 4 priority fixtures | 3/4, 238 mock units | 4/4, 260 mock units |
| Public Stage 4 six-company sample | 47/47 populated values, 389 mock units | 47/47 populated values, 389 mock units |
| Chromium same-origin Stage 2→3 and 3→4 imports | Passed, zero provider calls on import and retry | Passed, zero provider calls on import and retry |
| Whole-container kill during a Stage 4 batch | Passed, 62 billed and 62 reported | Passed, 38 billed and 38 reported |
| Live Runway | 4/6 after normalization, 3/6 literal, 78 units in 114.1 s | 3/6 after normalization, 3/6 literal, 78 units in 69.1 s |

The fresh Stage 4 build selected the visible CEO and cited visible text in the image-alt case. Both Stage 4 builds passed the legal-name and cumulative-funding fixtures. The fresh Stage 1 selected the cumulative total and still chose a namesake legal entity. The restart probes interrupted different numbers of calls. The public six-company sample is separate from the organizer’s scored economy workload. [Official rubric](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#rubric)

The fresh live response matched headquarters, CEO and founding year. Its CEO citation points to visible co-CEO text on a Runway site. Headcount and legal name were unknown, and the selected $8.5 million figure describes a Series A round. The verified build matched CEO, founding year and headcount literally. Its headquarters value matched after normalizing “New York” to “New York City.” Both trials used live search and ran at different times. The verified build remains the preferred submission based on this evidence. [Fresh live response](../dossier-runway.com.json) · [Verified live response](https://github.com/Xuefeng-Zhu/band-dossier/blob/e1ba438febd5940da9a8354e993179d26b42deaf/dossier-runway.com.json) · [Archive benchmark](https://github.com/Xuefeng-Zhu/band-dossier/blob/50ccde7f03310d0dfb79a1ef7d3b3b6fcf7e80bf/runs/run-12/NOTES.md#L49-L56)
