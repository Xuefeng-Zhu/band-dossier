# Band factory

**Buildathon draft.** Use the measurements and review evidence below when writing the entrant’s final account of the factory and its design choices. [Official submission instructions](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#check-and-submit)

## Seats

| Seat | Band identity | Codex model and effort | Responsibility |
| --- | --- | --- | --- |
| [Coordinator](mandates/coordinator.md) | `@frankzhu94/coordinator` | `gpt-6.2-sol`, medium | Sequence the work, issue complete handoffs and advance on a matching review verdict |
| [Implementer](mandates/implementer.md) | `@frankzhu94/implementer` | `gpt-6.2-sol`, medium | Own the current stage’s implementation and submit an exact commit for review |
| [Reviewer](mandates/reviewer.md) | `@frankzhu94/reviewer` | `gpt-6-astra`, high | Reproduce the checks independently, test gaps in the shipped suite and report a verdict |

All three seats used the same result checkout. A scoped host process handled Git writes and isolated Docker checks through a local queue, which let the seats work without interactive approval prompts. The linked mandates come from `81252e38b94285dbd73d08a7dfb833174a18324a`, the version used in room `908b7142-e4bb-49d1-9ebc-647504728e06`. [Full room export](room.json)

## Reproduce the setup

Use a fresh workspace with this repository cloned at `band-dossier/` and the organizer checkout at `sf-buildathon-2026/`. Prepare the organizer’s `.venv` and Chromium as described in [Verification](docs/verification.md), and start a rootless Docker daemon. From the workspace root, prepare an empty result repository and copy the same runner used in the judged build.

```bash
dossier_workspace=$(pwd -P)
dossier_result="$dossier_workspace/band-work/dossier-full-currency"
mkdir -p "$dossier_workspace/factory-prep" "$dossier_workspace/band-work/checks"
mkdir "$dossier_result"
git -C "$dossier_result" init -b main
mkdir -m 700 "$dossier_result/.band-continuation-operations"
printf '\n/.band-continuation-operations/\n' >> "$dossier_result/.git/info/exclude"
cp band-dossier/factory-tools/{continuation_operations,review_check,currency_probe,browser_probe}.py \
  "$dossier_workspace/factory-prep/"
DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock" \
  python3 -B "$dossier_workspace/factory-prep/continuation_operations.py" --currency-run serve
```

The socket above is the standard rootless Docker path on Linux. Run the host process with the socket path for your Docker installation, and keep it running until the final report. In a fresh Band room, attach three distinct Codex identities to the empty result checkout and configure their owner instructions from the linked mandates. Verify both direct mentions and the scoped runner on a disposable fixture before the judged dispatch.

From the result root, the Implementer calls the runner with `--currency-run commit N "message"`. The Reviewer calls `--currency-run check N FULL_COMMIT_SHA` and `--currency-run currency N FULL_COMMIT_SHA` for every stage, then adds `--currency-run browser N FULL_COMMIT_SHA` from Stage 2. Use `--currency-run status OPERATION_ID` to read each report. Each invocation uses `python3 -B` and the absolute path to `factory-prep/continuation_operations.py`. The runner confines commits to the active stage, checks the named revision in a clean checkout, and runs one stage at a time in isolation. Once the fixture checks work, use the dispatch template. [Judged dispatch](factory-tools/DISPATCH.md)

## Handoffs and recovery

The corrected run began with one human dispatch. The Coordinator opened the current specification and sent its full text and assignment in numbered direct mentions. Each seat ended its turn when its next step depended on a peer. The next direct mention triggered the work. The Implementer sent a candidate with its full commit ID and paused edits while the Reviewer checked it. A rejection went back to the Implementer with evidence and returned as a new commit. After accepting a stage, the Coordinator preserved its directory and copied it forward before opening the next specification. [Full room export](room.json)

The Reviewer rejected two candidates after their public organizer suites had passed.

- **Stage 1.** The first candidate could stop retrying the required exact-domain search after a string of free provider refusals. Audit scrubbing also missed very short synthetic credentials. The Implementer corrected both findings, and the Reviewer reran the failing cases and tested neighboring inputs before accepting `7d0a278`. [Stage 1 acceptance](room.json#L6806)
- **Stage 4.** The first candidate returned HTTP 422 for non-string domain entries in batch requests. The spec called for HTTP 400 for those wrong JSON types. The Implementer added member-type validation, and the Reviewer verified error precedence, unchanged state and zero provider traffic on those rejected writes before accepting `ce35abb`. [Stage 4 acceptance](room.json#L18028)

Stages 2 and 3 were accepted on their first submitted candidates. The separate review work included mock failure handling, historical reads and imports, evidence retention, and Chromium checks on the exact candidate revisions. [Run closeout](room.json#L18136)

## Delivery time and model usage

The measured interval from the first to the last seat text message was **1 h 56 min 44 s**. The interval from the sole human dispatch to the Stage 4 acceptance message was **1 h 57 min 3 s**. The room export contains 1,281 events, including the human dispatch, seat messages and tool activity. [Full room export](room.json)

| Seat | Input tokens | Cached input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Coordinator | 7,728,697 | 7,492,608 | 19,656 |
| Implementer | 51,548,555 | 51,087,488 | 180,905 |
| Reviewer | 20,871,559 | 20,481,920 | 98,161 |
| **Total** | **80,148,811** | **79,062,016** | **298,722** |

These are the final cumulative token counters from the three Codex seat sessions for this room. The input column includes cached tokens. No per-run model charge was available. The judged build used mock providers. The separate live Runway build reported 78 Nimble research units. [Runway response](dossier-runway.com.json)
