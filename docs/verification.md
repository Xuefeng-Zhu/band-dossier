# Verify Dossier

The Band run documented here accepted the four stage trees at the revisions below. Its final service revision is `ce35abb4b6d635e9d6a82cc928c3bf2884f16fa0`. The run used the seat mandates from `81252e38b94285dbd73d08a7dfb833174a18324a`. [Band room closeout](../room.json#L18136) · [Mandate provenance](https://github.com/Xuefeng-Zhu/band-dossier/commit/975667447c747c0a65c3f68fc1c4054797306a43)

| Folder | Accepted commit | Cumulative organizer checks | USD currency cases | Chromium captures | Independent checks |
| --- | --- | ---: | ---: | ---: | ---: |
| `stage-1/` | `7d0a2787ba895e84b22e33d3f24b43b6cb576eba` | 122/122 | 13/13 | — | 135/135 |
| `stage-2/` | `93c756e89bcc2bc08393fff839dfcdfe5548bc1d` | 134/134 | 13/13 | 12/12 | 80/80 |
| `stage-3/` | `e26382402c53f329108be229674d57cb79e73717` | 143/143 | 13/13 | 12/12 | 133/133 |
| `stage-4/` | `ce35abb4b6d635e9d6a82cc928c3bf2884f16fa0` | 153/153 | 13/13 | 12/12 | 190/190 |

The Reviewer checked the exact accepted revisions. The organizer checks ran in isolated Docker, and the currency probes exercised both page evidence and mock research. Chromium covered six routes at 375 px and 1440 px, including labels, overflow and sampled keyboard focus. Additional client behaviors were exercised in simulation. Stage 4 restart coverage in the Band run killed and relaunched the service process. That run left full-container restart, live-provider timing, real-browser replacement during upgrade and below-fold investor layout unverified. The judges run additional checks beyond the shipped suite. [Stage 4 verdict](../room.json#L18028) · [Participant guide](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#build-and-check-each-stage)

## Reproduce the organizer checks

Run this from a directory without existing `band-dossier/` or `sf-buildathon-2026/` checkouts. Use Python 3.12 or later and a running Docker daemon.

```bash
git clone --branch factory-v2 https://github.com/Xuefeng-Zhu/band-dossier.git
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

## Live Runway evidence

The repository includes the verbatim `GET /dossiers/runway.com` response from the accepted Stage 4 tree against the live Nimble endpoint. The request reached `ready` in 114.1 seconds and the response reports 78 research units. The four matches against the archive’s six-field Runway benchmark were headquarters, CEO, founding year and headcount. Headquarters matched after normalizing “New York” and “New York City.” The literal comparison matched three fields. The legal name was unknown, and the service selected a $2 million seed round as total funding. The hackathon scores research economy on a separate Stage 4 workload. [Live response](../dossier-runway.com.json) · [Archive benchmark](https://github.com/Xuefeng-Zhu/band-dossier/blob/50ccde7f03310d0dfb79a1ef7d3b3b6fcf7e80bf/runs/run-12/NOTES.md#L49-L56) · [Official rubric](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#rubric)
