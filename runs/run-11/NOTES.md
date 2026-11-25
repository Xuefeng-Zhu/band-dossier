# Band run 11 (Dossier, 4 seats) — notes

Started 2026-11-23 18:46 PST. Mandates work/band-dossier factory-v2 69e0536 (local only, NOT pushed). Exact copies: band-run-11/{coordinator,implementer,reviewer,spec-tester}.md (4569/4136/5127/2575 chars; sha256 393ae864…/862bbdc4…/952d7a89…(unchanged)/06950803…), byte-identical on VM ~/band-seats/mandates11/ (sha256 match) and in the seats (`band agent instructions show --reveal --json` content == file, True ×4). Changes vs run 10 (59a42f9): coordinator — after a scope ruling the spec tester turns every outcome it lists into one table-driven test before the next candidate; implementer — rerun the reviewer's earlier probes for that item on every fix; spec tester — after an ACCEPT start next phase wave 1 at once, add tests for an accepted phase only when the coordinator asks. Reviewer unchanged.
Dispatch = band-run-11/dispatch.txt (identical to run 10), sha256 5e69bad0234dc60bf3cae73a70e44d84945761ae2aee5e365d7b6d5ac37bb619 (VM ~/band-seats/run11-dispatch.txt, same sha). Vocab scan (band-run-4/vocabscan.py) on 4 mandates + dispatch: TOTAL 0.

## Setup (PST)
- Sandbox had restarted (no paramiko, no tunnel). pip install paramiko.
- INCIDENT (tunnel, same pattern as run 10): VM 127.0.0.1:18080 held by sshd from 35.162.213.8 = run 10's tunnel10.py in the previous sandbox instance, still alive (its log in our workspace stopped at 02:09 UTC, but it reconnected within seconds after I killed its sshd). Fix 18:47:50: `iptables -I INPUT -p tcp -s 35.162.213.8 --dport 22 -j DROP` (reversible) + kill its sshd. Existing rule for 35.162.191.92 left in place. Started band-run-11/tunnel11.py (= tunnel10.py) — tunnel up 18:47:51 PST, log band-run-11/tunnel.log, 0 × 407. This sandbox's SSH egress is 34.219.49.117.
- GET /v2/agents 200 from VM host (127.0.0.1:18443) and from a container (172.17.0.1:18443). No research/search probe. Forwarder nimble_fwd7.py pid 465923 still up. VM up 21h38m, disk 14%.
- Rotation (nothing deleted): result -> result-run10 (HEAD 979bba1), checks -> checks-run10; dossier-stage-{1,2}-handoff.md -> checks-run10/handoffs/*.toplevel.md; worktrees /tmp/dossier-stage1-fixes, -stage2-fixes, -stage2-admission -> checks-run10/dossier-<name>-worktree + `git worktree repair` (worktree list OK, log works). Fresh empty result (git init -b main, Factory <factory@factory.example.test>) + empty checks. (Older non-worktree /tmp/dossier-* scratch from runs 1–9 left as is.)
- Instructions set from ~/band-seats/mandates11/ (--instructions-stdin); show == file True ×4.
- Restart 18:48:43 via kept handle default-5341188d-… (all 4): Connected running=true; `band inbox --json` = [] for all 4.
- Room 16901889-946f-4ca0-9b6d-e8c2940dd316 "Factory run 11": `band chat new --as coordinator --with implementer --with reviewer --with spec-tester` + `band chat add` human 95a3f256-… + `band room rename`. 5 participants.
- Interrupt + detach default-5341188d-… ×4 -> codex 0 (5341188d sessions pruned, as expected). Restart --host-session default-16901889-… ×4 -> 4 codex all `--room 16901889…`, presence live, bound; room-11 inboxes []. NEXT RESTART HANDLE: default-0c70901d-… (run-9 room) is still listed for all 4 seats — leave it untouched.
- Desktop: Factory run 11 selected (xdotool 313,116), xscreensaver killed, xset s off -dpms.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-11.mkv (pid 777737). Monitors: logger11.py (777738) -> room11-log.jsonl; docker events -> docker-events11.log (777739); v11.py, exp11.py, units11.py (forwarder lines from 3567).
- DISPATCH 18:50:30 PST (02:50:30 UTC, epoch 1795488630): `band room send <room> "$(cat run11-dispatch.txt)" --mention fda466af-…` (coordinator). No other human messages.
- Stop rules: stage >45 min without ACCEPT (stage 1 deadline 19:35:30 PST); same reject 3x; stall >20 min; Nimble 402/quota; total units > ~2,500.

## Timeline (PST)
- 18:50:37 dispatch seen. 18:51:53 coordinator assignments to all three seats (handoff ~/band-work/dossier-stage-1-handoff.md, ledger R1–R32, R32 = live set); 18:52:08 spec pasted once in 8 parts + status to human. Kickoff 1.4 min.
- Commits bb3b5ea (18:55), 5e4c0ae (18:58), fe455a8 (19:00), 077969f (19:02). Implementer containers dossier-1124-impl-app/-mock (offline mock). 19:03:00 implementer "ready for Wave 1" at 077969f (12.5 min).
- ~19:03 reviewer live-route preflight from the VM host: 1 lite search (1 unit).
- 19:04:46 TESTS READY 1 wave 1 (35 HTTP cases + Docker/startup + serial R31 harness command) — 14.3 min (run 10: 9.2).
- 19:05:31 implementer: all 35 wave-1 cases errored before assertions — the spec tester's helper `http` shadowed the http module (checks.py:101). Implementer also found and fixed a sub-µs clock precision issue itself (a6fd394, 19:05) before any review.
- 19:08:33 LIVE CHECK SET fixed by reviewer: cloudflare.com, zoom.com, linear.app (verified values + sources; exact cumulative equity totals noted unverified) — 18.1 min (run 10: 8.5).
- 19:11:21 TESTS UPDATED (helper renamed; 35 cases) — suite bug cost ~6 min. 19:12:06 implementer wave 1 35/35 on a6fd394.
- 19:12:21 CANDIDATE 1 a6fd394 (35/35 in 27.1 s) — 21.9 min (run 10: 10.3). Delay = spec-suite helper bug + slower TESTS READY.
- INCIDENT (coordinator model latency): coordinator turn started 19:12:12 on CANDIDATE 1; its single model response (103 output tokens) took ~8.5 min (codex rollout: request 03:12:12Z -> reply 03:20:42Z). Room silent 19:12:21–19:20:42; not a hang (rollout kept the turn open). Reviewer runtime reaped as idle at 19:18 (normal; woken on mention).
- 19:20:57 review request to reviewer (8.6 min after CANDIDATE). Reviewer live builds (relay containers df-svc/df-web + 4 others) from ~19:21.
- 19:24:13 reviewer blocking R18 sent early (exact-domain search: recoverable 429 retried twice then abandoned; ready via research with zero accepted exact searches). 19:25:44 implementer R18 fix c7e3472 in isolated worktree (shared checkout kept at a6fd394).
- 19:25:59 reviewer blocking R26 (research citation = page Facts header treated as prose -> known) + R23 (valid grouped founding years 1,800 / 2,099 -> unknown). 19:27:15 blocking R28 (integrity-valid snapshot with wrong JSON type -> 204 and destination replaced; should be 422 and preserve). 19:27:46 implementer: R18+R23+R26 fixed in isolated b64ebd4 (four reviewer edge probes pass; replays the private live capture offline).
- 19:28:16 VERDICT 1 a6fd394 REJECT — 37.8 min; review 7.3 min (from request 19:20:57). Blocking R18, R23, R26, R28. Wave 1 35/35; isolated 122/122 claim 1 (82.4 s); three independent check groups pass (50-request race, cross-container round trip). Carried R32 LIVE baseline 9/15: Cloudflare 3/5 (72 u, 257 s), Zoom 4/5 (44 u, 132 s), Linear 2/5 (67 u, 225 s); 183 units; errors: Linear CPO as CEO + URL digits, Zoom founding year as headcount, Cloudflare portfolio financing as funding; all 16 excerpts found in provider replies.
- 19:29:16–19:29:32 implementer: R18/R23/R26 fixes pass the independent probe groups AND the reviewer's earlier reproductions; "original probe suite passed" on c7e3472 (new implementer rule behaved: reran reviewer's earlier probes). Offline replay of the 3 live captures reproduced all 18 baseline field values.
- 19:31:33 implementer: R28 fixed in isolated 35d51f2 (15 failing subcases at a6fd394, pass on fix; "all prior reviewer probes" pass).
- 19:32:34 TESTS UPDATED (35 -> 40 cases; both variants of each of the 4 blockers) — 4.3 min after REJECT (run 10: 2.0).
- 19:34:05 CANDIDATE 2 (posted as "CANDIDATE 1" again) 35d51f2 (40/40 + Docker gates in 50.1 s) — 43.6 min; 5.8 min after REJECT. Not yet forwarded to the reviewer by the coordinator at stop.
- STOP 19:35:35 PST: stage 1 hit the 45-min rule (deadline 19:35:30, no ACCEPT). `band stop` all 4 at 19:35:35–37 (agents + records kept). No scope ruling occurred (no item blocked twice), so the new ruling->table-test rule never fired; no ACCEPT, so the spec-tester-moves-on rule never fired.

## End (PST)
- 19:35:40 ffmpeg SIGINT -> ~/recording/factory-run-11.mkv (51.5 MB); logger11 + docker-events stopped. Room-11 sessions: interrupt ("agent is paused" — already stopped) + detach ×4.
- Inbox clear on kept handle default-0c70901d-… (run-9 room) 19:35:56: restart ×4 -> `band inbox --json` [] ×4; 4 codex all --room 0c70901d (no stray work, no messages); interrupt + `band stop` ×4 (NOT detached) 19:36:04 -> codex 0. default-0c70901d-… still listed on all 4 seats = next restart handle.
- Room export ~/band-seats/room11-messages.jsonl (10 pages, 932 msgs). Only human message: the dispatch.
- Result repo HEAD 35d51f2 (11 commits), main clean; no stage accepted. Branch stage1-r18-recovery (worktree /tmp/dossier-1124-r18 @35d51f2).
- Post-run (post11.sh, 19:36:21–19:38:08 PST) on result HEAD 35d51f2 (= unreviewed CANDIDATE 2; no stage accepted, so highest accepted = none and highest reached = stage 1 — one harness run covers both):
  - Isolated harness stage 1: completed, isolated, claimed 1, 122/122 (auth 51, dossiers 60, sample 11), fabrications 0, leaks 0; stage-2 probe fail as expected (0/12). checks/run11-final-s1, harness11-s1.out.
  - `harness check`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json) — expected (check11.out).
  - Live runway.com (live11.sh = live10.sh pattern; stage-1 at HEAD; bridge; NIMBLE_BASE_URL=http://172.17.0.1:18443 exactly — stage-1 research.py builds AsyncNimble from env, no provider-host check, so no aliased attempt needed): 03:37:43–03:38:08 UTC (19:37:43–19:38:08 PST, ~25 s), ready, spent_units 16 (forwarder 16: 7 lite searches, 10 extracts incl. 1 extract 500 counted by the forwarder; no research run). Saved band-run-11/dossier-runway.com.json.
    - legal_name "Runway Bidco, LLC" (opencorpdata LEI record) — WRONG (namesake; expected Runway AI, Inc.)
    - hq_city "New York" (rocketreach "based in New York, New York") — CORRECT city (strict "New York City" differs)
    - ceo "Rent The" (LinkedIn snippet "Chief Executive Officer & President at Rent The Runway") — WRONG (namesake company + truncated span; expected Cristóbal Valenzuela)
    - founded_year 2018 (cbinsights runwayml) — CORRECT
    - headcount_range "201-500" (comparably "Runway has 230 employees") — CORRECT
    - funding_total 859,500,000 (cbinsights "Runway raised a total of $859.5M") — CORRECT, EXACT (first exact funding)
    - Score 4/6 lenient (HQ, founded, headcount, funding); 3/6 strict (founded, headcount, funding exact). Run 10: 4/6 lenient / 2 strict (CEO right, headcount wrong); run 8: 5/6 lenient.
- Cleanup: removed dossier-live11; no containers; only bridge/host/none networks. Forwarder GET /v2/agents 200 at end.
- Copies: handoff (stage 1) -> checks/handoffs/; Hark post-run outputs -> checks/hark-post/. band-run-11/result = result repo (HEAD 35d51f2, 11 commits, clean, branch stage1-r18-recovery incl.); band-run-11/checks (2.5 MB, includes reviewer-stage1 live captures + review report); room-messages.jsonl (932 msgs), room11-log.jsonl, docker-events11.log, nimble_fwd11.log (forwarder lines since this run's start), live11-docker.log, units11.py etc. Implementer worktree /tmp/dossier-1124-r18 (@35d51f2, same as main) left on VM, registered.
- Side effect: my interrupts on the room-9 handle posted "no active turn to interrupt" task events into room 9 (19:36); no text messages.

## Live check set and how the gates behaved
- Set (reviewer, 19:08:33, 18.1 min — slow): cloudflare.com, zoom.com, linear.app (Linear = private generic-name case). Exact cumulative equity totals marked unverified by the reviewer.
- Per candidate (reviewer, of 15): S1 a6fd394 9/15 (Cloudflare 3/5, Zoom 4/5, Linear 2/5); CANDIDATE 2 never reviewed.
- Reviewer-only live rule: HELD (implementer, spec tester, coordinator 0 units; implementer replayed captures offline).
- Carried quality bar: BEHAVED — live errors (Linear CPO as CEO, URL digits, Zoom founding year as headcount, Cloudflare portfolio financing as funding) carried as baseline; blocking came only from stated spec requirements (R18 exact search recovery, R23 grouped years, R26 header citations, R28 import validation).
- New rules: (1) ruling -> table tests: NOT EXERCISED (no item blocked twice; only one verdict). (2) implementer reruns reviewer probes: BEHAVED — implementer reported the reviewer's earlier reproductions/probe suite passing on each fix (19:29:16, 19:29:32, 19:32:34 "All prior reviewer probes"). (3) spec tester moves on after ACCEPT: NOT EXERCISED (no ACCEPT).

## Nimble accounting (forwarder nimble_fwd11.log; same unit model as runs 7–10)
| Seat / window | units (forwarder) | notes |
|---|---|---|
| Reviewer preflight (host, ~19:03) | 1 | |
| Reviewer live S1 a6fd394 (3 relays + 2 research runs, 19:21–19:24) | 173 | self-report 183 (72/44/67); 22 extract 500 + 4 extract 504 refused (0) |
| Implementer / spec tester / coordinator | 0 / 0 / 0 | |
| Hark final runway (dossier-live11) | 16 | service 16 |
| TOTAL through forwarder | 190 (seats 174 = reviewer 100%) | |
No 402/429 through the forwarder; tunnel 0 × 407. Far under ~2,500. No Hark research probe (GET /v2/agents only).

## Stage time table (min, from dispatch 18:50:30)
| | kickoff | live set | TESTS w1 | CAND 1 | review req | VERDICT 1 | TESTS UPD | CAND 2 | end |
|---|---|---|---|---|---|---|---|---|---|
| S1 run 11 | 1.4 | 18.1 | 14.3 (+suite bug fixed 20.9) | 21.9 | 30.4 | REJECT 37.8 (review 7.3) | 42.1 | 43.6 | stopped 45.1 (45-min rule; CAND 2 unreviewed) |
| S1 run 10 | 1.7 | 8.5 | 9.2 | 10.3 | 10.5 | REJECT 20.4 | 22.4 | 25.9 | ACCEPT 34.0 |
Total run wall: 45.1 min (18:50:30–19:35:35).

Reject reasons: S1 V1 a6fd394 — R18 recoverable exact-domain 429 retried twice immediately then abandoned, build ready via research with zero accepted exact searches; R23 valid comma-grouped founding years (1,800 / 2,099) -> unknown; R26 research citation equal to the page's Facts header accepted as prose -> known (CEO, legal name); R28 integrity-valid snapshot with wrong JSON type / incomplete citations -> 204 and destination replaced (should be 422, preserved).

## Bottlenecks (where the 45 min went)
1. Coordinator model latency 8.5 min (19:12:12–19:20:42) between CANDIDATE 1 and the review request: one model response, not a hang; the coordinator sits on the critical path for every review request.
2. Spec-tester wave 1 shipped with a helper that shadowed the http module: all 35 cases errored; ~6–7 min lost (TESTS READY 14.3 -> working suite 20.9) and one wasted implementer run.
3. Live set fixed late (18.1 min vs 8.5) — did not delay the candidate this time, but the reviewer spent its first 18 min on prep.
4. Implementer itself was fast and clean: self-found the sub-µs clock bug before review (run 10's R5 block), fixed all 4 blockers in an isolated worktree before/at the verdict, CAND 2 5.8 min after REJECT.

## Next generic tweaks (proposal, not applied)
- Implementer: send CANDIDATE to the coordinator AND the reviewer at once; the reviewer starts on it without waiting for the coordinator's request (the coordinator still records and can veto). Removes the coordinator's model latency from the critical path (8.5 min here).
- Spec tester: before TESTS READY, smoke-run the suite once against any running build (or the mock) and confirm at least one case reaches an assertion; a suite that errors before assertions is not ready.
- Reviewer: fix the live check set first (within ~10 min of the phase opening), before deeper probe prep.
- Operator stop rule: if a candidate was posted before the 45-min mark, let its review finish (cap e.g. +12 min) before stopping — run 11 stopped with a 4-blocker-fix candidate posted 1.4 min before the deadline.
- Operator: each new sandbox leaves the previous sandbox's tunnel alive and auto-reconnecting (35.162.191.92 run 9, 35.162.213.8 run 10). Give the tunnel a lifetime (exit after N hours, or check a run-id file on the VM) so it stops by itself.

## Submission note
Run 11 ran factory-v2 69e0536 (= band-run-11/*.md). Stage 1 reached, not accepted (stopped at 45 min with CANDIDATE 2 35d51f2 unreviewed). Best full run remains run 6 (e104885). Nothing pushed/merged/submitted.

## Left running / state
VM up; sandbox tunnel11.py (fresh 18:47:51, log band-run-11/tunnel.log, 0 × 407); VM iptables DROP tcp:22 from 35.162.191.92 (run-9 sandbox tunnel) AND from 35.162.213.8 (run-10 sandbox tunnel, added this run) — remove with `sudo iptables -D INPUT -p tcp -s <ip> --dport 22 -j DROP` if needed; VM forwarder nimble_fwd7.py pid 465923 (GET /v2/agents 200 at end). Seats Stopped (agents + records kept); room-11 sessions interrupted + detached; inboxes empty; restart handle = default-0c70901d-… (run-9 room) on all 4 seats (stopped, not detached). No containers, no extra networks. ~/band-work/result, checks, dossier-stage-1-handoff.md and /tmp/dossier-1124-r18 worktree left in place for run 11 (rotate to -run11 before run 12).
