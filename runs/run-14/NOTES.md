# Band run 14 (Dossier, 4 seats) — notes

**Outcome: run lost to a VM outage.** The VM (35.252.223.41) stopped answering on every port, from this sandbox and from outside checkers (check-host.net, 3 nodes: TCP timeout), starting ~23:01 PST (07:01 UTC). That was mid stage 1, during the review of CANDIDATE 2. It was still unreachable at the last check (see "End" below). No post-run steps could be done: no stop, no export, no harness, no live runway build. Nothing pushed, merged or submitted.

Started 2026-11-23 22:26 PST. Mandates: work/band-dossier factory-v2 088bc45 (local only, NOT pushed). Exact copies are in band-run-14/{coordinator,implementer,reviewer,spec-tester}.md (4719/4550/5574/3021 bytes):
- coordinator 0402e630f560660d7a248f213e44f2e1d69a6d8093b1af45cced1d0d0dfc8643 (same as run 13)
- implementer 4a342549e299fa9a873bbb4ded801fe390fb27388003e107e1e0b976ba794d37 (new)
- reviewer 9c5de97f7723ccc63fb5774ef4d7f940b927bc3ceb51c3e8f00e8eb87abf6cd2 (new)
- spec-tester defa91dcbf996af3f260b0e8a829fb7ae6ff1e86adea2d176b11e69848dad15c (same as run 13)

The copies on the VM (~/band-seats/mandates14/) have matching sha256s, and each seat's stored instructions match its file (`band agent instructions show --reveal --json` .instructions.content == file, True ×4).

Changes vs run 13 (51ed20d):
- Implementer: after a REJECT, post the next candidate as soon as its own regression tests and the current suite pass, without waiting for TESTS UPDATED. When that arrives, run it on the candidate and report.
- Implementer: before a fix that changes how outside data is chosen or filtered, replay every saved outside response on the previous candidate and on the new commit, list each changed output with its reason, and fix regressions first.
- Reviewer: updated tests that arrive during a review are run on the candidate as part of that review.

Dispatch: band-run-14/dispatch.txt, identical to runs 10–13. sha256 5e69bad0234dc60bf3cae73a70e44d84945761ae2aee5e365d7b6d5ac37bb619 (VM ~/band-seats/run14-dispatch.txt has the same sha). Vocab scan (band-run-4/vocabscan.py) on the 4 mandates + dispatch: TOTAL 0.

Seats and models are the same as run 13 (agent templates unchanged): coordinator gpt-6.2-sol medium, implementer gpt-6.2-astra high, reviewer gpt-6.2-sol high, spec tester gpt-6.2-sol medium.

## Setup (PST)
- VM: up 1d1h17m, disk 14% (125 GB free). VM :22 connections came only from 34.219.49.117 (this sandbox). The iptables DROP rules for 35.162.213.8 and 35.162.191.92 were already in place, so nothing new needed blocking.
- Rotation (nothing deleted):
  - ~/band-work/result -> result-run13 (HEAD 7d85854); checks -> checks-run13.
  - dossier-stage-{1,2}-handoff.md -> checks-run13/handoffs/.
  - The four worktrees impl-1124-0510-s1 (9eda30d), impl-1124-0536-s2 (4655e23), impl-1124-0548-s2-live (752d054) and impl-s2-0602-r29 (7d85854) -> checks-run13/<name>-worktree, then `git -C result-run13 worktree repair <4 paths>`. `worktree list` and `log` work in each.
  - Run-13 /tmp scratch: 87 entries (hark-owned, mtime 04:58–06:20 UTC 11/24, incl. live13, run13-acc, run13*.tgz, dossier-*, playwright profiles, inbox13/ids13) -> checks-run13/tmp-1124/. /tmp/bd.log (06:24 UTC, not a run-13 artifact) was left in place.
  - Fresh empty result repo (git init -b main, Factory <factory@factory.example.test>) and an empty checks dir.
- Instructions were set from mandates14 while the seats were stopped (--instructions-stdin); show == file True ×4.
- 22:27:50 fresh tunnel: killed tunnel13.py (sandbox pid 14939), whose VM sshd released 127.0.0.1:18080. Started band-run-14/tunnel14.py (= tunnel13.py), log band-run-14/tunnel.log; new VM sshd pid 1017265 on 18080. 0 × 407.
- 22:27:57 GET /v2/agents 200 from the VM host (127.0.0.1:18443) and 200 from a container (172.17.0.1:18443), through forwarder nimble_fwd7.py pid 465923. No research or search probe. Forwarder log baseline: 4862 lines (run-14 lines are those after that; units14.py uses i < 4862).
- 22:28:10 restart ×4 on handle default-7f5ae855-… -> Connected. `band inbox --json` returned [] ×4, so there was nothing to ack.
- Room 2c5136e2-45c5-4f8d-b90a-30a9c13f28dd "Factory run 14": created with `band chat new --as devstar3071/coordinator --with …implementer --with …reviewer --with …spec-tester`, then `band chat add` human 95a3f256-2926-47fb-9714-683d18827970 and `band room rename`. 5 participants.
- 22:28:50 interrupt on the 7f5ae855 handle ×4 ("interrupt requested"); room-13 sessions reported "agent is paused" (already stopped). Every old host session on all 4 seats (all rooms incl. 7f5ae855) was detached: rc 0 ×54, 0 failed -> codex 0.
- 22:29 restart --host-session default-2c5136e2-… ×4 -> Connected. 4 codex, all `--room 2c5136e2…`, presence live, bound. Room-14 inboxes [] ×4.
- Desktop (Xvfb :1): "Factory run 14" selected (xdotool 317,116); xscreensaver killed, xset s off -dpms. Screenshot: band-run-14/shot-pre.png.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-14.mkv (pid 1019774). Monitors: logger14.py (1019775) -> ~/band-seats/room14-log.jsonl; docker events -> docker-events14.log (1019776).
- DISPATCH 22:29:44 PST (06:29:44 UTC): `band room send <room> "$(cat run14-dispatch.txt)" --mention fda466af-278f-4a2b-a6c4-f273d7922757` (coordinator). No other human message was sent.
- Stop rules as given: S1 deadline 23:14:44, review cap 23:26:44.

## Timeline (PST, first-seen in room log; minutes from dispatch)
- 22:29:59 dispatch seen. 22:31:30 coordinator: stage-1 spec in 9 parts (handoff ~/band-work/checks/stage-1-handoff.md, R1–R20) + status to the human. Kickoff 1.8 min (run 13: 1.3).
- 22:34:02 reviewer: live route verified (1 lite search from a 2-CPU/3-GiB container, 1.97 s); R20 sources placed in the handoff. Noted that `harness check` is offline-only, so it will use `harness run --mode isolated`.
- Commits: 239a750 (22:33), 0598138 (22:35), 4f904c3 (22:36), 6857ec1 (22:37).
- 22:37:04 spec tester smoke found an R2 startup blocker (WebRouter.get_search_provider). At the same time the implementer found the tester's runner shadowing http.client.HTTPException. Both were fixed within a minute (smoke-run rule caught a real product bug before CANDIDATE).
- 22:38:05 CANDIDATE 1 6857ec1 to coordinator + reviewer: 8.4 min (run 13: 7.4). Wave 1 23/23. TESTS READY 1 wave 1 arrived at the same second (8.4; run 13: 7.6).
- 22:40:21 reviewer probes ready. 22:41:07 PROPOSED/FIXED LIVE SET: cloudflare.com, figma.com, linear.app (SEC + company disclosures), 11.4 min (run 13: 9.2).
- 22:42:07 blocking R6 (malformed JSON without bearer -> 400 instead of 401). 22:43:23 blocking R16 (export after research closes the connection: datetime in provider journal). 22:44:39 blocking R14 (a recoverable first 429 is never retried, so zero successful exact searches). 22:45:56 blocking R15 (multi-sentence research citations shortened and accepted). 22:47:57 R15 live: Cloudflare funding $7.03B included post-IPO convertible notes (SEC 8-K).
- 22:44:39 implementer isolated fixes: R16 d12a48d (journal dates -> JSON; 0/3 -> 3/3) and R6 5d03484 (12/21 -> 21/21).
- ~22:48–22:52 the spec tester's codex process exited after turn_complete (presence dormant, binding bound; codex count 3). It respawned when the verdict mentioned it (codex 4 by 22:52).
- 22:50:44 VERDICT 1 6857ec1 REJECT: 21.0 min; review 12.7 min (run 13: 15.2 / 7.8). Isolated: completed/isolated/revision match/claim 1, 122/122, stage-2 probe fails as expected. Wave 1 23/23. Independent probes 6/14. Blocking R6, R14, R15, R16 (+ live R15 funding scope).
- 22:51:29 reviewer explained the mock throttle semantics to the implementer.
- 22:52:45 TESTS UPDATED 1: 6 new REJECT regressions (test_R06_…, test_R14_…, …), 2.0 min after REJECT (run 13: 1.3).
- 22:53:15 implementer: R15 live fixes in 3f27c49. "Offline replay matched all 192 captured responses on both revisions. Two field/citation pairs changed": Cloudflare funding $7,032,050,000 -> $332,000,000 and Linear CEO Jori Lallo -> Karri Saarinen, each with its reason. This is the NEW replay rule exercised before nomination. R14 backoff + Retry-After (5/5 recovery checks).
- 22:54:01 CANDIDATE 2 3f27c49: 24.3 min, 3.3 min after REJECT (run 13 S1: 16.7 / +1.5). Wave 1 incl. the 6 regressions 29/29. TESTS UPDATED had already arrived before nomination, so the "don't wait" rule was not tested on the critical path. 22:55:02 implementer reran TESTS UPDATED on the clean candidate (29/29) and reported to coordinator + reviewer, as the new rule says.
- 22:54–22:57 reviewer fresh live round on CAND 2 (3 research starts; units 200 -> ~367).
- 22:56:02 reviewer blocking R15 regression on 3f27c49: two verified equity-only totals (Cygnus $12,500, Novel Harbor $4.2M) became unknown. The implementer's 192-response replay was over live captures; these are offline stand-in cases, not live captures.
- 22:59:35 implementer: second live capture shows Linear's $35M Series B selected as total funding (single round, no cumulative claim); fixing this together with the two equity-only regressions.
- ~23:00:30 last successful VM read (msgs=1080; last event 23:00:20 reviewer tool_call). No VERDICT 2 had been seen.
- **23:01–23:02 VM unreachable** (tunnel "dropped" at 07:02:03 UTC; then SSH banner EOF, then TCP timeouts on 22/80/443/8080/3389; outside checkers time out too). Sandbox egress to other hosts was fine (github.com:22, gitlab.com:22, 8.8.8.8:53 OK).

## Stage time table (min from stage open; S1 = dispatch 22:29:44)
| | kickoff | live set | TESTS w1 | CAND 1 | VERDICT 1 | TESTS UPD | CAND 2 | VERDICT 2 | end |
|---|---|---|---|---|---|---|---|---|---|
| S1 run 14 | 1.8 | 11.4 | 8.4 | 8.4 | REJECT 21.0 (review 12.7) | 23.0 (+2.0) | 24.3 (+3.3) | none (review in progress, 2 blocking notes sent) | VM lost ~31.5 |
| S1 run 13 | 1.3 | 9.2 | 7.6 | 7.4 | REJECT 15.2 (review 7.8) | 16.5 (+1.3) | 16.7 (+1.5) | ACCEPT 20.0 | ACCEPT 20.0 |
| S1 run 12 | 1.4 | 2.4 | 10.3 | 10.0 | REJECT 21.6 (11.6) | 28.0 (+6.3) | 32.2 (+10.6) | – | stopped 37.2 (402) |

Reject reasons: S1 V1 6857ec1 — R6 auth precedence (malformed body before bearer), R14 no retry of a recoverable 429 on the canonical search, R15 multi-sentence research citations shortened and accepted + live funding including debt (Cloudflare $7.03B), R16 export fails after research (datetime in journal). Open blocking notes on CAND 2 3f27c49 (no verdict): R15 regression (equity-only totals now unknown), R15 single round as total (Linear $35M Series B). Same-reason count: R15 2× (V1, CAND 2 notes), below 3×.

## How the new rules behaved (as far as the run got)
1. Implementer doesn't wait for TESTS UPDATED: NOT TESTED on the critical path. TESTS UPDATED (+2.0) beat the fix (+3.3), so the implementer ran it before posting anyway, and the CANDIDATE included the 6 regressions. The follow-on duty (rerun the updated suite on the clean candidate and report to coordinator + reviewer) WAS followed at 22:55:02.
2. Implementer replays every saved outside response on both commits before a data-selection fix: EXERCISED. 192 captured responses replayed on both revisions; each changed field was listed with its reason (Cloudflare funding, Linear CEO). It did not catch the reviewer's offline equity-only regression, because those cases are stand-in fixtures rather than saved live responses. Proposed tweak: the replay must also cover the reviewer's and the spec tester's offline cases.
3. Reviewer runs updated tests that arrive during review: not observable. The tests arrived before CAND 2 and before VERDICT 1's follow-up; there is no reviewer report for CAND 2.

## Nimble accounting (forwarder; last read ~23:00 PST before the outage)
| Seat / window | units | notes |
|---|---|---|
| Hark setup GET /v2/agents ×2 | 0 | |
| Reviewer preflight | 1 | lite search (attributed host?uid0) |
| Reviewer live CAND 1 (cloudflare/figma/linear) | ~167 | 1 research start; 24 extract 500 + 5 504 refused |
| Reviewer live CAND 2 (in progress) | ~199 | 2 more research starts; total extract errors 57×500, 7×504 |
| Implementer / spec tester / coordinator | 0 / 0 / 0 | reviewer-only live held |
| TOTAL through forwarder (to ~22:58) | 367 | n402 = 0 |
The forwarder log after 22:58 was not read (VM down). No Hark final runway build was run.

## Incidents
1. **VM outage from ~23:01 PST.** Cause not established. Candidates: the GCP lab project/account (devstar3071@gcplab.me) expiring or reclaiming the VM (lab accounts have been deleted before: devstar2309, Nov 16), or a host freeze under load (4 codex + reviewer live builds + spec-tester stacks). A load freeze is less likely: the kernel would still answer TCP SYN, but every port times out. Hark has no working GCP access from this sandbox: the ADC refresh fails ("problem refreshing your current auth tokens"), gcloud has no active account, and compute.googleapis.com returned no response. So VM status could not be checked, and the VM could not be restarted.
2. Spec tester's codex process exited while idle between turns (dormant/bound) and respawned on the next mention. Harmless here. New behaviour vs run 13 (codex stayed 4).

## End (PST)
- TCP checks to 35.252.223.41:22 kept timing out at 07:03–07:21:47 UTC (last 23:21:47 PST): an outage of more than 20 minutes, past the stall rule. Run ended by outage at ~23:01 PST (31.5 min after dispatch).
- tunnel14.py: the first instance exited at ~07:09 UTC while retrying. It was restarted at 07:17:49 UTC (sandbox pid 3196, appending to tunnel.log) and is still retrying.
- Not done (VM down): band stop ×4; interrupt/detach room 14; inbox clear; leftover container/network removal; ffmpeg stop (the recording ~/recording/factory-run-14.mkv may be truncated or lack a clean trailer); room export; forwarder log copy; isolated harness on HEAD / highest accepted; `harness check`; live runway.com build and grading.
- Highest accepted stage: none (S1 not accepted). Highest reached: stage 1, CAND 2 3f27c49 (review in progress).
- Live runway grade: not available (no build).

## Proposed generic mandate tweaks (not applied)
- Implementer: the pre-nomination replay covers every offline case the reviewer and spec tester have published (their probe fixtures), not only saved live responses, so equity-only/stand-in regressions are caught before CANDIDATE.
- Reviewer: still ~12.7 min to VERDICT 1 with 4 blocking items found progressively (22:42–22:48). Send the verdict as soon as the isolated check and the blocking set are complete; continue live as non-blocking notes for the next round.
- Operator (not a mandate): check the VM's reachability and lab-account lifetime before a run; keep a way to restart the VM (working gcloud auth) for recovery.

## Left running / state
- Sandbox: tunnel14.py (pid 3196, restarted 07:17:49 UTC) still running and retrying the VM connection (log band-run-14/tunnel.log, 0 × 407). It will re-establish VM:18080 automatically if the VM comes back on the same IP.
- VM: unreachable. If it returns, it will be in an unknown state. Seats may restart as Connected, the room-14 sessions may resume, and the recording, logger and docker-events monitors are probably gone. Before anything else, someone must run `band stop` ×4, interrupt + detach room 14, export room 14 (exp14.py), copy nimble_fwd7.log lines after 4862, and do the run-14 post-run.
- Nothing pushed, merged or submitted.

## Files (band-run-14/)
coordinator/implementer/reviewer/spec-tester.md (mandates), dispatch.txt, tunnel14.py + tunnel.log, logger14.py, v14.py, exp14.py, units14.py, mon.sh, m2.sh, w.sh, shot-pre.png, .out/.last (monitor scratch). Room log, export, forwarder log, result, checks, harness outputs and dossier json are NOT present: they live on the unreachable VM.
