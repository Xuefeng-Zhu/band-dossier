# Band run 1 (submitted Dossier run) — notes

Started 2026-11-22 21:14 PST.

## Setup done
- jamd restarted 21:15 PST; `band whoami` = Frank Zhu @frankzhu94.
- Codex 0.171 lists gpt-6.2-sol and gpt-6.2-astra (efforts low..ultra).
- Mandates updated in work/band-dossier (factory-v2, commit 7ff1ba4, not pushed): coordinator gpt-6.2-sol/medium, implementer gpt-6.2-astra/high, reviewer gpt-6.2-sol/high, Harness: Codex. Vocabulary scan vs challenges/dossier/vocabulary.json: 0 hits.
- VM: WORKSPACE=/home/hark; kickoff ~/sf-buildathon-2026 (7043245, clean, .venv present); result repo ~/band-work/result (git init -b main, empty); checks ~/band-work/checks.
- Per-seat git identity via spawn wrappers ~/band-seats/codex-<seat>.sh (GIT_AUTHOR/COMMITTER = Coordinator/Implementer/Reviewer).
- Nimble relay: sandbox tunnel.py (CONNECT relay -> sandbox egress proxy that injects the vault key; reverse tunnel to VM 127.0.0.1:18080) + VM ~/band-seats/nimble_fwd.py (plain HTTP on 127.0.0.1:18443 and 172.17.0.1:18443 -> https://sdk.nimbleway.com). Test GET /v2/agents -> 200 from VM host and from a container. Key never on VM.
- Agent create dry-run OK: transport codex-app-server, approval never, sandbox danger-full-access, auth subscription.

## Blocker 1 (21:20 PST)
`band agent create` -> "Remote agent limit reached." Account has 20 owned agents (limit). Frank approved deleting old coordinator/implementer/reviewer + tkh-1005f-* (there are 7 tkh agents, not 6).
jamd IPC bulkDeletePeers only deletes agents with a local peer record ("not_found_locally"); the VM has no local records and no agent keys. Deleting needs the Band console (app.band.ai) or Band Desktop UI.

## Restart with NEW empty Band account (2026-11-22 ~21:48 PST)
- Old Blocker 1 moot: Frank switched to empty account devstar3071@gcplab.me. jamd restarted 21:49 PST; `band whoami` = Star Developer 3071 @devstar3071 (user id 95a3f256-2926-47fb-9714-683d18827970).
- Tunnel (sandbox tunnel.py) still up; VM nimble_fwd 18443 -> GET /v2/agents 200.
- Spawn wrappers now also export NIMBLE_API_KEY=via-proxy NIMBLE_BASE_URL=http://127.0.0.1:18443 (forwarder; key injected sandbox-side).
- Seats created 21:52 PST (band agent create, transport codex-app-server, auth subscription, approval never, sandbox danger-full-access, cwd ~/band-work/result, instructions = mandate text via stdin, session=seat name):
  - devstar3071/coordinator  fda466af-278f-4a2b-a6c4-f273d7922757  gpt-6.2-sol medium
  - devstar3071/implementer  1c97788f-67c0-4f64-9e20-777947b4fb08  gpt-6.2-astra high
  - devstar3071/reviewer     014190fc-9ba1-450a-b24e-897cc0b411c4  gpt-6.2-sol high
  - grant files_outside_workspace=on for all three.
- Band Desktop on Xvfb :1 + xfce (same account). Onboarding: Codex enabled, starter teams all OFF, background OFF.
- Room: 991bd6e5-9088-436b-959d-0bfa5b55419d "Factory run" (created by coordinator via `band chat new`, human added via `band chat add`, renamed by human).
- Recording: ffmpeg x11grab 2 fps -> VM ~/recording/factory-run.mkv (started 21:55 PST), Desktop showing the room.
- DISPATCH sent 21:55:57 PST (05:55:57 UTC) via `band room send` mentioning coordinator. Text: band-run-1/dispatch.txt (vocab scan 0 hits). No further human messages.

## Stage 1 timeline (PST)
- 21:55:57 dispatch -> 21:57:05 coordinator posts 8-part handoff to implementer AND reviewer (ledger R1–R29, 35-min time box), status note to human 21:57:15.
- 22:04 implementer dev harness s1-1; 22:07 reports 122/122 stage-1 shipped checks, next suite fails as expected.
- 22:10:27 commit b87af76809806e1be0ff8ab330d498bd6703eb93 (author Implementer); 22:10:57 CANDIDATE stage-1.
- 22:11:11–13 coordinator sends 8-part "exact-commit review" request to reviewer.

## Blocker 2 (22:32 PST) — reviewer deadlock, STOPPED monitoring and reported
- Reviewer's FIRST turn (started 21:57:09) never ended. It built probes in ~/band-work/checks/reviewer-stage1, then waited in-turn with repeated Codex `sleep` items (every ~30–60 s) for the review request.
- Band delivers queued mentions only between turns: `band inbox --as devstar3071/reviewer` shows all 16 coordinator messages (handoff 1–8 + review 1–8) still un-acked.
- Reviewer asked the coordinator twice (22:21:59, 22:28:28) for the exact revision; coordinator woke each time and ended its turn in ~7 s without posting (it had already sent it). Loop >= 2 rounds -> stopped per brief, no intervention.
- No human message after the dispatch. VM, seats, room, Desktop and recording left RUNNING so Frank can choose.
- Options: (a) operator-only unstick, no room message: `band runtime interrupt --as devstar3071/reviewer --host-session default-991bd6e5-9088-436b-959d-0bfa5b55419d` (ends the turn; queued review request then delivers) — arguably an intervention; (b) abandon this room, fix mandates (reviewer/implementer: "end your turn after each reply; never sleep or poll for messages — new messages only arrive between turns"; coordinator: never tell a seat to "wait for" a message inside its turn), fresh room + fresh result repo, rerun.
