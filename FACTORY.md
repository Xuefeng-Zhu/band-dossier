# Band factory

**Buildathon draft.** Use the measurements and review evidence below when writing the entrant’s final account of the factory and its design choices. [Official submission instructions](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#check-and-submit)

## Seats

| Seat | Band identity | Responsibility |
| --- | --- | --- |
| [Coordinator](mandates/coordinator.md) | `@frankzhu94/coordinator` | Sequence the work, issue complete handoffs and advance on a matching review verdict |
| [Implementer](mandates/implementer.md) | `@frankzhu94/implementer` | Own the current stage’s implementation and submit an exact commit for review |
| [Reviewer](mandates/reviewer.md) | `@frankzhu94/reviewer` | Reproduce the checks independently, test gaps in the shipped suite and report a verdict |

Each seat ran Codex with `gpt-6.2-sol`, medium reasoning effort, subscription authentication and a workspace-write sandbox. All three used the same result checkout. A scoped host process handled Git writes and isolated Docker checks through a local queue, which let the seats work without interactive approval prompts.

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
cp band-dossier/factory-tools/continuation_operations.py "$dossier_workspace/factory-prep/"
DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock" \
  python3 -B "$dossier_workspace/factory-prep/continuation_operations.py" --currency-run serve
```

The socket above is the standard rootless Docker path on Linux. Run the host process with the socket path for your Docker installation, and keep it running until the final report. In a fresh Band room, attach three distinct Codex identities to the empty result checkout and configure their owner instructions from the linked mandates. Verify both direct mentions and the scoped runner on a disposable fixture before the judged dispatch.

From the result root, the Implementer calls the runner with `--currency-run commit N "message"`. The Reviewer calls `--currency-run check N FULL_COMMIT_SHA` and uses `--currency-run status OPERATION_ID` to get the result. Each invocation uses `python3 -B` and the absolute path to `factory-prep/continuation_operations.py`. The runner confines writes to the active stage and checks the named revision in a clean checkout. Its Docker command runs one stage at a time in isolated mode.

## Handoffs and recovery

The corrected run began with one human dispatch. The Coordinator opened the current specification and sent its full text and assignment in numbered direct mentions. Each seat ended its turn when its next step depended on a peer. The next direct mention triggered the work. The Implementer sent a candidate with its full commit ID and paused edits while the Reviewer checked it. A rejection went back to the Implementer with evidence and returned as a new commit. After accepting a stage, the Coordinator preserved its directory and copied it forward before opening the next specification. [Full room export](room.json)

The Reviewer’s findings led to changes in three stages.

- **Stage 1.** The Reviewer found explicit foreign currencies misclassified as USD and valid dollar mentions dropped because geographic context was mistaken for a currency qualifier. Follow-up review caught `A $12M` being treated like `A$12M`. The accepted extractor handles these distinctions in page evidence and in verification of provider research claims.
- **Stage 3.** A concurrent history request could see only part of a refresh. The accepted version copies a consistent history snapshot under the read lock.
- **Stage 4.** Unrelated extracts used up the budget before the service could follow relevant canonical sources. The accepted version prioritizes relevant lineage, and the Reviewer reran the ancestry and restart checks.

## Delivery time and model usage

The measured interval from the first to the last seat text message was **1 h 31 min 35.907 s**. The room export contains 1,309 events from the run, including the human dispatch, seat messages and tool activity.

| Seat | Input tokens | Cached input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Coordinator | 8,367,457 | 8,173,440 | 23,699 |
| Implementer | 53,129,879 | 52,706,560 | 161,857 |
| Reviewer | 32,116,392 | 31,777,408 | 90,807 |
| **Total** | **93,613,728** | **92,657,408** | **276,363** |

The Codex session telemetry includes cached tokens in the input column. Subscription billing dollars were unavailable. The separate live Runway build reported 80 Nimble research units. [Live response](dossier-runway.com.json)
