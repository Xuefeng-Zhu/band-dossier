# Band run 12 (Dossier, 4 seats) — notes

Started 2026-11-23 19:42 PST. Mandates work/band-dossier factory-v2 a104c2b (local only, NOT pushed). Exact copies: band-run-12/{coordinator,implementer,reviewer,spec-tester}.md (4719/4168/5349/2846 bytes; sha256 0402e630…/c8902133…/a3a64603…/90b091f9…), byte-identical on VM ~/band-seats/mandates12/ (sha256 match) and in the seats (`band agent instructions show --reveal --json` .instructions.content == file, True ×4). Changes vs run 11 (69e0536): implementer sends CANDIDATE to coordinator + reviewer in one message; reviewer starts on any CANDIDATE without waiting for a review request; coordinator only re-sends when reviewer was left out; spec tester smoke-runs each wave (suite loads, >=1 case reaches assertions) before TESTS READY, helper names distinct from stdlib; reviewer proposes live check set first thing, within ~10 min, before writing probes.
Dispatch = band-run-12/dispatch.txt (identical to runs 10/11), sha256 5e69bad0234dc60bf3cae73a70e44d84945761ae2aee5e365d7b6d5ac37bb619 (VM ~/band-seats/run12-dispatch.txt, same sha). Vocab scan (band-run-4/vocabscan.py) on 4 mandates + dispatch: TOTAL 0.
Seats/models (verified in codex rollouts of the run-11 threads; agent templates unchanged, per-session overrides null): coordinator gpt-6.2-sol medium, implementer gpt-6.2-astra high, reviewer gpt-6.2-sol high, spec tester gpt-6.2-sol medium.

## Setup (PST)
- Same sandbox instance as run 11 (tunnel11.py pid 1995 still running, SSH egress 34.219.49.117). No stale tunnels from other IPs: VM :22 connections only from 34.219.49.117. Existing iptables DROP rules for 35.162.191.92 (run 9) and 35.162.213.8 (run 10) left in place.
- Fresh tunnel 19:44:01: killed tunnel11.py (pid 1995) + its VM sshd (775046/775114, held 127.0.0.1:18080); started band-run-12/tunnel12.py (= tunnel11.py) -> log band-run-12/tunnel.log, 0 × 407.
- GET /v2/agents 200 from VM host (127.0.0.1:18443) and from a container (172.17.0.1:18443) at 19:44:12–13. No research/search probe. Forwarder nimble_fwd7.py pid 465923. VM up 22h33m, disk 14% (125 GB free).
- Rotation (nothing deleted): result -> result-run11 (HEAD 35d51f2), checks -> checks-run11; dossier-stage-1-handoff.md -> checks-run11/handoffs/dossier-stage-1-handoff.toplevel.md; worktree /tmp/dossier-1124-r18 -> checks-run11/dossier-1124-r18-worktree + `git worktree repair` (worktree list OK, log works); other run-11 scratch /tmp/dossier-1124-{impl-evidence,sample.py,smoke.py} -> checks-run11/tmp-1124/ (avoid name collisions; run 12 is also UTC 11/24). Fresh empty result (git init -b main, Factory <factory@factory.example.test>) + empty checks.
- Instructions set from ~/band-seats/mandates12/ while stopped; show == file True ×4.
- 19:45 restart ×4 on run-9 handle default-0c70901d-…: Connected; `band inbox --json` [] ×4 (nothing to ack); codex 4.
- Room 28167bda-fc6d-4899-8ce3-eaac355735f4 "Factory run 12": `band chat new --as devstar3071/coordinator --with …implementer --with …reviewer --with …spec-tester` + `band chat add` human 95a3f256-… + `band room rename`. 5 participants.
- Interrupt + detach EVERY old host session on all 4 seats (991bd6e5, b321b008, 5a38f7fe, 89977895, 7eb89d0c, 0c70901d [run-9 restart handle, interrupt ok], caa7ba06, 4569f696 [room 10], c80c81bf, 16901889 [room 11], 5341188d): detach rc 0 ×43 -> codex 0. Remaining sessions per seat: parked `default` + room-12 session only.
- 19:46 restart --host-session default-28167bda-… ×4 -> Connected, 4 codex all `--room 28167bda…`, presence live, bound; room-12 inboxes [] ×4.
- Desktop (Xvfb :1): Factory run 12 selected (xdotool 317,116); xscreensaver killed, xset s off.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-12.mkv (pid 816345). Monitors: logger12.py (816346) -> room12-log.jsonl; docker events -> docker-events12.log (816347); v12.py, exp12.py, units12.py (forwarder lines from 3766).
- DISPATCH 19:47:12 PST (03:47:12 UTC, epoch 1795492032): `band room send <room> "$(cat run12-dispatch.txt)" --mention fda466af-…` (coordinator). No other human messages.
- Stop rules: stage >45 min without ACCEPT (stage 1 deadline 20:32:12 PST), but a candidate posted before the deadline gets its review finished (cap +12 -> 20:44:12); same reject 3x; stall >20 min; Nimble 402/quota; total units > ~2,500.

## Timeline (PST)
- 19:47:20 dispatch seen. 19:48:35 coordinator: stage-1 assignments + spec pasted once in 8 parts (handoff ~/band-work/checks/dossier-stage-1-handoff.md, ledger R1–R25, R24 = live set, R25 = isolated harness/verdict); 19:48:51 status to human. Kickoff 1.4 min.
- 19:49:36 reviewer PROPOSED LIVE CHECK SET (2.4 min; run 11 18.1, run 10 8.5): mercury.com (private, namesake Mercury Marine + third-party CEO quote in Mercury's annual letter; Immad Akhund, 2017, Mercury Technologies, Inc.), vercel.com (Guillermo Rauch, 2015; $300M Series F round / $9.3B valuation as traps), fastly.com (Kip Compton, 2011, San Francisco, Fastly, Inc., 1,140 employees -> 1001-5000). Primary-source references (company pages, SEC 10-K). New reviewer rule BEHAVED.
- INCIDENT (coordinator model latency, again): coordinator turn started 19:49:36 (woken by the live-set mention), steered 2 more messages in, then one model response took until ~19:57 (rollout silent 19:51–19:57). Did not block anything this time: nobody waited on the coordinator.
- 19:51:07 reviewer live-route preflight: 1 lite search (1 unit), resource-limited container with host networking.
- Commits 64aab34 (19:53), 38a09db (19:55), 23779f9 (19:56).
- 19:57:11 CANDIDATE 1 23779f9 sent to coordinator AND reviewer in one message (new implementer rule BEHAVED) — 10.0 min (best ever; run 10 10.3, run 11 21.9). Wave 1 39 passed / 2 reviewer-owned skips in 36.9 s (implementer ran the tester's in-progress suite before it was announced).
- 19:57:27/19:57:42 TESTS READY 1 wave 1 (39 checks + 2 reviewer-owned skips, R1–R23) — 10.3 min (run 11 14.3, run 10 9.2). Spec tester reported its own checkout runs (39/39, 2 skips) => smoke-run rule BEHAVED; no suite-loading bug this time. Suite hash changed once after CANDIDATE (accounting diagnostics); implementer reran (19:58:27) 39/39.
- No coordinator review request was sent; reviewer "setup ready" 19:59:58 and started on the candidate (live builds df-svc/df-web/dossier-review-live-* from ~20:00, 2.8 min after CANDIDATE) — reviewer-starts-without-waiting rule BEHAVED.
- 20:03:45 reviewer blocking R20 sent early (research excerpts with uppercase labels "CEO:"/"HQ:" discarded as page headers). 20:05:16 second R20 class (recovered exact search after a dropped connection + 503s never extracts its discovered pages). 20:07:18 implementer: both fixed in isolated worktree /tmp/stage1-impl-labels at b63db2a (commits 43952cc, b63db2a), reviewer HTTP probes + 8 earlier independent groups + wave 1 pass; offline replay of the live capture keeps all 18 values (rule "rerun reviewer's earlier probes" still followed).
- 20:07:33 coordinator R25 confirmation (suite hash tie-in) to reviewer.
- 20:08:49 VERDICT 1 23779f9 REJECT — 21.6 min; review 11.6 min from CANDIDATE. Blocking R20 ×2 (uppercase-label research citations; recovered exact search skips gathering). R25 isolated 122/122 claim 1 (34.3 s); wave 1 39 + 2 skips; 8 independent groups pass. R24 LIVE carried baseline 10/18 corroborated: Mercury 73 u / 217 s, Vercel 79 u / 224 s, Fastly 73 u / 260 s (225 units reconciled; 17/17 excerpts verbatim). Errors carried: namesake founding year, requisition number + department count as headcount, regional headcount, verb attached to CEO name, single round as funding total; Vercel legal name unknown.
- 20:09:04 implementer: shared checkout now at b63db2a, waiting for TESTS UPDATED.
- 20:15:08/20:15:23 TESTS UPDATED 1 (both R20 repros added; reproduced on 23779f9, pass on b63db2a) — 6.3 min after REJECT (run 11 4.3, run 10 2.0). 20:16:54 implementer: R20 regressions pass at b63db2a but one mixed-load accounting discrepancy in the tester's harness (mock 68 vs service 71 via a forwarding proxy with backlog 5); 20:18:55 spec tester: proxy backlog 5 vs mock 128 confirmed, cause not established, wave 1 now hits the mock directly under mixed load. 20:19:10 coordinator R18/R20/R25 handoff update.
- 20:19:26 CANDIDATE 2 (posted as "CANDIDATE 1" again) b63db2a to coordinator + reviewer — 32.2 min; 10.6 min after REJECT (run 11 5.8, run 10 5.6). Reviewer started at once (isolated harness on b63db2a 20:19–20:20: completed, isolated, claim 1, 122/122; 3 live builds 20:20–20:22: Mercury 75 u / 86 s with HQ "Andover" — Mercury Systems namesake from ir.mrcy.com — so it ran a Mercury repeat build (20:23, 52 u / 64 s, HQ back to San Francisco) = reproducible-drop gate being applied; replays of both captures on both revisions).
- 20:23:22 (04:23:22 UTC) Nimble POST /v2/agents/runs -> 402 during the reviewer's Mercury repeat: {"error_type":"billing_not_allowed","block_reason":"trialNoQuota","message":"This account cannot be billed for a Web Search Agent run"} (from the reviewer's provider-replay.json; same block as run 8).
- STOP 20:24:25 PST (37.2 min): Nimble 402/quota stop rule. `band stop` ×4 at 20:24:25–26 (agents + records kept). CANDIDATE 2 review was mid-flight (no VERDICT 2); 45-min deadline (20:32:12) not reached; no reject reason repeated.

## End (PST)
- 20:24:45 ffmpeg SIGINT -> ~/recording/factory-run-12.mkv (45.9 MB, "Exiting normally"); logger12 + docker-events stopped. Leftover spec-tester mock stack (s1-spec-9db32085f25a-{service,web,proxy,recovery} + network; offline, no live) removed.
- Inbox check (needs a running worker): restarted coordinator on room 12 -> inbox []; created an empty room 7f5ae855-5208-4a2b-8161-d88b1df93a83 renamed "Factory restart handle (no work)" (no human or agent text in it) so a future run has a restart handle; restarted implementer/spec tester/reviewer on room 12 -> `band inbox --json` [] ×4 (nothing to ack); interrupt ×4; `band stop` ×4; then interrupt + `band detach --host-session default-28167bda-…` ×4 (room 12 detached). No new room-12 text after the stop. codex 0.
- Finding: detached old-room sessions REAPPEAR (presence dormant, binding detached) in `band sessions` whenever the seat is running (server-side room membership), so detaching does not remove a restart handle; it is pruned only from the stopped listing. Handle for next run: default-7f5ae855-… (or any room session after a running seat lists it).
- Room export ~/band-seats/room12-messages.jsonl (10 pages, 971 msgs; 36 text). Only human text message: the dispatch.
- Result repo HEAD b63db2a (5 commits: 64aab34, 38a09db, 23779f9, 43952cc, b63db2a), main clean; no stage accepted. Branch fix-stage1-research-label (worktree /tmp/stage1-impl-labels @b63db2a = main) left on VM.
- Post-run (post12.sh, 20:27:20–20:29:34 PST) on HEAD b63db2a (= CANDIDATE 2, review interrupted; highest accepted = none, highest reached = stage 1 at the same commit, so one harness run covers both):
  - Isolated harness stage 1: completed, isolated, revision b63db2a, claimed 1, stage 1 pass (122 checks), stage-2 probe fail as expected. checks/run12-final-s1, harness12-s1.out.
  - `harness check`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json) — expected (check12.out).
  - Live runway.com (live12.sh = live11.sh pattern; stage-1 at HEAD; bridge; NIMBLE_BASE_URL=http://172.17.0.1:18443): 04:28:29–04:29:34 UTC (20:28:29–20:29:34 PST, ~65 s), ready, spent_units 62 (forwarder 60: 7 lite searches, 65 extracts incl. 12 extract 500 refused, research start 402 trialNoQuota -> research blocked). Saved band-run-12/dossier-runway.com.json.
    - legal_name "Runway Ai, Inc." (bizprofile.net "Foreign Legal Name") — CORRECT lenient (case "Ai" vs "AI" fails strict)
    - hq_city "New York" (fundediq "based in New York") — CORRECT lenient (strict "New York City" differs)
    - ceo "Cristobal Valenzuela" (fundediq "listed as CEO at Runway") — CORRECT lenient (strict: missing accent ó)
    - founded_year 2018 (corpdigest) — CORRECT
    - headcount_range "1-10" (leadiq "workforce spans 9 departments") — WRONG (expected 201–500)
    - funding_total 859,500,000 (cbinsights "raised $859.5M over 9 rounds") — CORRECT, EXACT
    - Score 5/6 lenient (ties best: run 8), 2/6 strict (founded, funding). Run 11: 4/6 lenient / 3 strict; run 10: 4/6 / 2.
- Cleanup: dossier-live12 removed; no containers; only bridge/host/none networks. Forwarder GET /v2/agents was 200 at setup; not re-probed after the 402 (GET is free; research quota is the blocked item).

## How the new rules behaved
1. Implementer sends CANDIDATE to coordinator + reviewer at once: WORKED both times (19:57:11, 20:19:26). Reviewer started without a review request (live builds ~2.8 min after CAND 1; isolated harness within ~0.5 min of CAND 2). Coordinator never sent a review request and was off the critical path; its own model latency recurred (19:49–19:57) but cost nothing. Candidate->verdict 11.6 min (run 11: candidate->request 8.6 + review 7.3 = 15.9).
2. Spec tester smoke-runs each wave before TESTS READY: WORKED — TESTS READY carried the tester's own checkout run (39 pass, 2 reviewer skips); no import/collection bug; implementer ran it cleanly first time. Wave 1 at 10.3 min (run 11 14.3, with a working suite only at 20.9). Side effect: TESTS UPDATED took 6.3 min, and the spec tester's mixed-load accounting check flaked once (proxy backlog), costing ~4 min before CAND 2.
3. Reviewer fixes the live check set first (~10 min): WORKED — proposed at 2.4 min (run 11 18.1, run 10 8.5) with primary-source references and a private namesake case (Mercury). Coordinator recorded it in the handoff.
Carried rules: reviewer-only live HELD (implementer/spec tester/coordinator 0 units; implementer replayed captures offline). Quality bar carried, never blocking (10/18 baseline). Reproducible-drop gate in use on CAND 2 (Mercury HQ namesake drop -> repeat build) when the 402 hit. Ruling->table-test and post-ACCEPT rules NOT EXERCISED (no item blocked twice, no ACCEPT).

## Nimble accounting (forwarder nimble_fwd12.log = nimble_fwd7.log lines after 3766; same unit model as runs 7–11)
| Seat / window | units (forwarder) | notes |
|---|---|---|
| Reviewer preflight (19:51) | 1 | 1 lite search |
| Reviewer live CAND 1 23779f9 (3 builds, ~20:00–20:05) | 196 | self-report 225 (73/79/73); 19 extract 500 refused; 3 research runs |
| Reviewer live CAND 2 b63db2a (3 builds + Mercury repeat, 20:20–20:24) | 235 | 27 extract 500 refused; 3 research runs ok + 1 research 402 trialNoQuota |
| Implementer / spec tester / coordinator | 0 / 0 / 0 | |
| Hark final runway (dossier-live12) | 60 | service 62; 12 extract 500; research 402 |
| TOTAL through forwarder | 492 (seats 432 = reviewer 100%) | |
Tunnel 0 × 407. Far under ~2,500 — the 402 is the Nimble trial's research quota (research runs only), not the unit cap. Searches/extracts still worked after it (final build). No Hark research probe (GET /v2/agents only).

## Stage time table (min, from dispatch)
| | kickoff | live set | TESTS w1 | CAND 1 | review start | VERDICT 1 | TESTS UPD | CAND 2 | end |
|---|---|---|---|---|---|---|---|---|---|
| S1 run 12 | 1.4 | 2.4 | 10.3 | 10.0 | ~12.8 (no request needed) | REJECT 21.6 (review 11.6) | 28.0 | 32.2 | stopped 37.2 (Nimble 402 trialNoQuota; CAND 2 review in progress) |
| S1 run 11 | 1.4 | 18.1 | 14.3 (working 20.9) | 21.9 | 30.4 (request) | REJECT 37.8 (review 7.3) | 42.1 | 43.6 | stopped 45.1 (45-min rule) |
| S1 run 10 | 1.7 | 8.5 | 9.2 | 10.3 | 10.5 | REJECT 20.4 | 22.4 | 25.9 | ACCEPT 34.0 |
Total run wall: 37.2 min (19:47:12–20:24:25).

Reject reasons: S1 V1 23779f9 — R20 research excerpts with uppercase prose labels ("CEO:", "HQ:") discarded as page headers -> unknown; R20 after a dropped exact search + 503 targeted searches, the recovered exact search's discovered sole source never extracted -> unknown.

## Bottlenecks
1. Nimble trial research quota ran out (402 trialNoQuota on POST /v2/agents/runs) at 20:23 — ended the run, not the factory. Each reviewer live round runs 3–4 research starts; the account can't sustain more research runs.
2. REJECT -> CAND 2 took 10.6 min (run 10/11 ~5.7): TESTS UPDATED 6.3 min, then a flaky mixed-load accounting check in the tester's harness (proxy backlog) took another ~4 min to settle.
3. Review of CAND 1 took 11.6 min (live builds ~4.5 min each in parallel + 8 probe groups); fine, but the slowest step.

## Next generic tweaks (proposal, not applied)
- Reviewer: before starting a repeat live build to test a reproducible drop, first replay the new capture on the previous revision offline (and the old capture on the new one); only spend a fresh live build if replay is inconclusive. Saves research quota.
- Spec tester: TESTS UPDATED within ~5 min; regression cases for a REJECT go first, harness changes (proxy/backlog) only if a case is flaky, and a flaky case gets reported rather than silently retried.
- Spec tester: under concurrent load, test against the mock directly; a fault-injection proxy in front must have a listen backlog at least as large as the mock's.
- Operator: a 402 on research runs only (trialNoQuota) could be a "degrade" not a "stop" — continue without research runs (search/extract still work) — if Frank prefers; current rule stops.
- Operator: after stop, inbox checks need a running worker; keep the empty "Factory restart handle (no work)" room (7f5ae855) as the standing restart/inbox handle instead of old run rooms.

## Submission note
Run 12 ran factory-v2 a104c2b (= band-run-12/*.md). Stage 1 reached, not accepted (CAND 2 b63db2a review interrupted by the Nimble 402 stop at 37.2 min). Best full run remains run 6 (e104885). Nothing pushed/merged/submitted.

## Left running / state
VM up; sandbox tunnel12.py (pid 7128, fresh 19:44:01, log band-run-12/tunnel.log, 0 × 407); VM iptables DROP tcp:22 from 35.162.191.92 and 35.162.213.8 (unchanged); VM forwarder nimble_fwd7.py pid 465923. Seats Stopped (agents + records kept); room-12 sessions interrupted + detached; inboxes empty; restart handle = default-7f5ae855-… ("Factory restart handle (no work)", stopped, not detached). No containers, no extra networks. ~/band-work/result (HEAD b63db2a), checks, /tmp/stage1-impl-labels worktree left in place for run 12 (rotate to -run12 before run 13). Nimble research runs currently refused (trialNoQuota).
