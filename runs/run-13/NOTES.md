# Band run 13 (Dossier, 4 seats) — notes

Started 2026-11-23 21:00 PST. Mandates work/band-dossier factory-v2 51ed20d (local only, NOT pushed). Exact copies: band-run-13/{coordinator,implementer,reviewer,spec-tester}.md (4719/4168/5464/3021 bytes; sha256 0402e630…/c8902133…/a099c6db…/defa91dc…), byte-identical on VM ~/band-seats/mandates13/ (sha256 match) and in the seats (`band agent instructions show --reveal --json` .instructions.content == file, True ×4). Changes vs run 12 (a104c2b): reviewer step 5 — replay captured outside responses offline on both commits first, spend a new live run only when replay can't settle a drop; spec tester — regression tests within ~5 min of a REJECT, load tests directly against the outside-service stand-ins, flaky tests reported by name. Coordinator + implementer unchanged (sha = run 12).
Dispatch = band-run-13/dispatch.txt (identical to runs 10–12), sha256 5e69bad0234dc60bf3cae73a70e44d84945761ae2aee5e365d7b6d5ac37bb619 (VM ~/band-seats/run13-dispatch.txt, same sha). Vocab scan (band-run-4/vocabscan.py) on 4 mandates + dispatch: TOTAL 0.
Seats/models same as run 12 (agent templates unchanged): coordinator gpt-6.2-sol medium, implementer gpt-6.2-astra high, reviewer gpt-6.2-sol high, spec tester gpt-6.2-sol medium (rollouts of this run show gpt-6.2-sol / gpt-6.2-astra).

## Setup (PST)
- NEW NIMBLE KEY (vault f2256d31-…, service nimble, injected by the sandbox proxy; old 26572aa4 removed). Key never printed, written or put on the VM.
- 20:58:59 fresh tunnel: killed tunnel12.py (pid 7128); started band-run-13/tunnel13.py (= tunnel12.py) -> band-run-13/tunnel.log. VM 127.0.0.1:18080 re-bound by our new sshd. 0 × 407.
- 20:59:06–07 GET /v2/agents 200 ×2 from VM host (127.0.0.1:18443) + 200 from a container (172.17.0.1:18443) through forwarder nimble_fwd7.py pid 465923. No research/search probe by Hark. (GET can't prove research quota; the reviewer's 3 research starts at ~21:11 succeeded, n402 = 0 → new key has research quota.)
- Stale tunnels: VM :22 connections only from 34.219.49.117 (this sandbox). iptables DROP for 35.162.213.8 and 35.162.191.92 already present; nothing new to block.
- VM up 23h49m, disk 14% (125 GB free).
- Rotation (nothing deleted): ~/band-work/result -> result-run12 (HEAD b63db2a), checks -> checks-run12 (incl. dossier-stage-1-handoff.md); worktree /tmp/stage1-impl-labels -> checks-run12/stage1-impl-labels-worktree + `git worktree repair` (worktree list OK, log works); run-12 /tmp scratch (/tmp/stage1-*, implementer-router, impl-labels-before.log, impl-recovery-before.log, dossier-stage1-spec-_ug712zp — all 03:51–04:24 UTC 11/24) -> checks-run12/tmp-1124/. Older /tmp/dossier-stage1-* scratch from 11/23 runs left in place. Fresh empty result (git init -b main, Factory <factory@factory.example.test>) + empty checks.
- Instructions set from ~/band-seats/mandates13/ while stopped (--instructions-stdin); show == file True ×4.
- 21:00:00 restart ×4 on handle default-7f5ae855-… ("Factory restart handle (no work)"): Connected; `band inbox --json` [] ×4 (nothing queued, nothing to ack).
- Room b6369be9-32e1-4840-bdf5-2d435d1a461d "Factory run 13": `band chat new --as devstar3071/coordinator --with implementer --with reviewer --with spec-tester` + `band chat add` human 95a3f256-… + `band room rename`. 5 participants.
- Interrupt on 7f5ae855 (×4 "interrupt requested"); rooms 9/11/12 sessions (0c70901d, 16901889, 28167bda) "agent is paused" (already stopped). Detach every old host session on all 4 seats (all rooms incl. 7f5ae855): detach rc 0 ×50 -> codex 0.
- 21:01:04 restart --host-session default-b6369be9-… ×4 -> Connected, 4 codex all `--room b6369be9…`, presence live, bound; room-13 inboxes [] ×4.
- Desktop (Xvfb :1): Factory run 13 selected (xdotool 317,116); xscreensaver killed, xset s off -dpms. Screenshot band-run-13/shot-pre.png.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-13.mkv (pid 879843). Monitors: logger13.py (879845) -> room13-log.jsonl; docker events -> docker-events13.log (879847); v13.py, exp13.py, units13.py (forwarder lines from 4247), m2.sh.
- DISPATCH 21:02:05 PST (05:02:05 UTC): `band room send <room> "$(cat run13-dispatch.txt)" --mention fda466af-…` (coordinator). No other human messages.
- Stop rules: stage >45 min without ACCEPT (+ candidate posted before 45 min gets its review, cap 57 min); same reject reason 3x; stall >20 min; Nimble 402/quota; total units > ~2,500.

## Timeline (PST)
- 21:02:08 dispatch seen. 21:03:24 coordinator stage-1 assignments + spec in 8 parts (handoff ~/band-work/dossier-stage-1-handoff.md, R1–R29) + status to human. Kickoff 1.3 min.
- Commits 3f3c58d (21:06), bb0aa9c (21:08).
- 21:08:58 spec tester ambiguity (R5 unsupported methods / zero successful searches) -> 21:09:13 coordinator ruling (unknown path 404 not_found; unsupported method 404 or 405; refused calls aren't successful searches).
- 21:09:28 CANDIDATE 1 bb0aa9c to coordinator + reviewer (7.4 min; run 12 10.0). 14/14 wave-1 tests (implementer ran the suite before announcement).
- 21:09:43 TESTS READY 1 wave 1 (7.6 min; run 12 10.3).
- 21:10:29 implementer self-found R5 ruling failures (4 routes 401) -> isolated f7c81f0.
- 21:10:59 reviewer probes ready + 1-unit WebRouter preflight; 21:11:14 PROPOSED LIVE CHECK SET cloudflare.com, linear.app, vercel.com (9.2 min; run 12 2.4) with SEC/DPA primary sources. 21:11:29 coordinator asked Linear to satisfy R29 (namesake + third-party attribution); 21:17:33 reviewer: Linear qualifies (Descript/Sierra customer stories; namesake Linear Technology Corp).
- ~21:11–21:16 reviewer live builds for CAND 1: 3 research starts, 214 units.
- 21:13:30 reviewer blocking R5/R25 (imports with 1e309 / nested -1e999 -> 500 text/plain); 21:14:16 blocking R5 routing (401 on unmatched paths/methods).
- 21:14:31 TESTS READY wave 2 (11 groups).
- 21:15:01 implementer: both fixed in isolated 9eda30d (wave 1 14/14, wave 2 11/11, reviewer probes pass).
- 21:15:32 TESTS UPDATED (routing regression; reproduced 4 × 401 on bb0aa9c, 15/15 on f7c81f0) — BEFORE the verdict.
- 21:17:18 VERDICT 1 bb0aa9c REJECT — 15.2 min; review 7.8 min from CANDIDATE. Blocking R5 (routing 401) + R5/R25/R27 (nonfinite import -> 500).
- 21:18:34 TESTS UPDATED (import regression; 16/16 on 9eda30d) — 1.3 min after REJECT (run 12 6.3).
- 21:18:49 CANDIDATE 2 9eda30d — 16.7 min; 1.5 min after REJECT (run 12 10.6).
- 21:22:06 VERDICT 2 9eda30d ACCEPT — 20.0 min (run 10 34.0; first stage-1 ACCEPT since run 10). Isolated 122/122 (90.7 s), next-stage probe fails as expected, wave 1 16/16, wave 2 11/11; no new live run on CAND 2 (change can't affect live output; reused CAND-1 live).
- 21:23:22 Stage 2 opened (coordinator status to human + 5-part spec, R1–R53, handoff ~/band-work/dossier-stage-2-handoff.md). Stage-2 deadline 22:08:22, review cap 22:20:22.
- Commits 240cab8 (21:25), f993807 (21:28), 292c68d + fd7fe53 (21:30).
- 21:30:57 TESTS READY 2 wave 1 (28 groups incl. Chromium desktop + 375 px) — 7.6 min from stage open. 21:31:12 coordinator asked the spec tester for a separate supplemental suite (R34/R36/R42/R45/R46).
- 21:32:28 CANDIDATE stage-2 fd7fe53 (28/28 in 42 s) to coordinator + reviewer — 9.1 min (run 10 S2 15.7).
- 21:32:43/21:32:58 spec tester ambiguity R34/R36 (same value from two providers at one URL) -> coordinator ruling (one candidate; either provider).
- 21:33:13 reviewer probes ready; 21:33:28 live set kept (cloudflare/linear/vercel; 9 verified S1 values, 226-unit baseline).
- INCIDENT 21:34:18–21:35:02: reviewer's stage-2 review stacks (dossier-review-s2-*-922314/-926730) and harness relays (df-svc-*, df-web-*) were killed/removed (exit 137); Vercel live build had finished (78 u), Cloudflare + Linear builds lost. Cause not established from docker events (kill events have no actor; the reviewer's own rollout contains `docker rm -f $n` cleanup traps — most likely a reviewer cleanup, not another seat). Reviewer did not re-spend on the rejected revision.
- 21:35:29 reviewer blocking R31/R34 (render refusal -> static-only founded 1993 / HQ Anchorage kept as candidates); 21:36:30 blocking R38/R8 (HTML evidence route 200 for invalid domains). 21:37:15 TESTS READY wave 2 (13/13). 21:38:46 implementer: both fixed in isolated a31b6ef + 4655e23.
- 21:40:32 VERDICT 2-1 fd7fe53 REJECT — 17.2 min (review 8.1). Blocking R31/R34 + R8/R38. Isolated 122/122 + 12/12 claim 2; wave 1 28/28, wave 2 13/13; browser 375×812 + 1440×1000 pass. Live partial (Vercel 78 u, 3 verified).
- 21:42:18 TESTS UPDATED (3 named regressions) — 1.8 min after REJECT. 21:43:19 CANDIDATE 4655e23 — 20.0 min; 2.8 min after REJECT.
- 21:43–21:47 reviewer fresh live round on 4655e23 (change affects live; 3 builds, ~225 u). 21:47:06 blocking R29 live regression (Vercel funding $863M -> $9.3B valuation; Linear CEO Karri Saarinen -> Jori Lallo). 21:47:52 implementer replay: two causes. 21:48:07 coordinator ruling R31/R34 (hidden link/image destinations can't qualify visible prose) + R36/R52 (valuation candidates stay ranked by Appendix A). 21:48:52 reviewer: "full live replay" on the same captured pages — frozen S1 selector returns Karri/$863M, 4655e23 returns Jori/$9.3B (replay on both commits = new rule).
- 21:50:23 VERDICT 2-2 4655e23 REJECT — 27.0 min (review 7.1). Blocking R31/R34/R29 (Linear CEO from an excerpt whose company match is only in an invisible image URL; reproduced offline on both selectors). Vercel valuation carried under R36/R52 ruling. Live 240 u / 7 verified (baseline 226 / 9).
- 21:50:38 coordinator round-2 scope ruling (visible characters only; hidden-only negation leaves prose eligible). 21:52:24 spec tester 8-row table `test_R31_R34_visible_prerequisites_and_negation_table`. 21:53:10 spec tester reported a GET /dossiers/vercel.com 5-s timeout on fc916d9 BY NAME/log instead of retrying (flaky-report rule) — real regression (raw PDF parsing), fixed by implementer in 481c4e3 21:55:57. 21:53:40 TESTS UPDATED (3.3 min after REJECT); re-confirmed on 481c4e3 21:56:42.
- 21:57:43 CANDIDATE 481c4e3 — 34.4 min; 7.3 min after REJECT (implementer waited for TESTS UPDATED on the exact revision; coordinator re-relayed twice).
- 21:58–22:01 reviewer fresh live round (3 builds, ~222 u) + replays. 21:59:59 reviewer: replay on both commits shows Vercel CEO Rauch -> "Benjamin Netanyahu" (photo-caption headline) on 481c4e3; 22:00:45 coordinator inline-markup clarification; 22:01:30 fresh live run confirms.
- 22:03:47 VERDICT 2-3 481c4e3 REJECT — 40.4 min (review 6.1). Blocking R29 (Vercel CEO Netanyahu; reproduced on frozen S1 capture, prior S2 capture and fresh capture). Linear fixed (Karri). Live 240 u / 6 verified. 22:04:17 coordinator: "R29 has blocked twice" + gate restated.
- 22:04:17 implementer isolated fix 7d85854 (provider document.body.innerText on render; render budget across fields); 22:04:47 spec tester asked for the provider response shape for the regression. 22:07:04 implementer: 7d85854 on shared checkout, wave 1 28/28 + wave 2 16 (+1 optional skip), "the spec tester has the revision for a targeted regression" — NOT a CANDIDATE (no CANDIDATE message, waiting on TESTS UPDATED).
- STOP 22:08:34 PST: stage 2 hit 45 min (deadline 22:08:22) without ACCEPT and with no CANDIDATE posted after VERDICT 2-3, so no review to wait for. `band stop` ×4 22:08:34–36 (agents + records kept). Same-reason count at stop: R31/R34 2× (S2 V1 render refusal, V2 invisible qualifiers — different defects), R29 2× (V2, V3) — below 3×.

## End (PST)
- 22:08:40 ffmpeg SIGINT -> ~/recording/factory-run-13.mkv (100.2 MB, clean exit); logger13 + docker events stopped ~22:09.
- Leftover spec-tester stack removed 22:09:03: containers stage2-spec-1001-1006239-{old,app,mock} (images stage2-spec-1001-1006239:stage1/:stage2, df-dossier-mockweb; offline) + network stage2-spec-1001-1006239-network. After: 0 containers, only bridge/host/none.
- Inboxes: restart on the 7f5ae855 handle failed ("peer not found" — it had been detached/pruned), parked `default` can't be restarted, so (as in run 12) restarted ×4 on room 13 and interrupted each immediately (22:09:41): `band inbox --json` [] ×4 (nothing to ack); then interrupt + `band stop` ×4 + `band detach --host-session default-b6369be9-…` ×4 (rc 0) -> codex 0. No room-13 messages after 22:07 (export checked) — the restart posted nothing.
- Restart handle for next run: default-7f5ae855-… reappeared in the stopped listing for all 4 seats after this restart (detached, listed) — use it (same finding as run 12: detached sessions come back once the seat runs).
- Room export ~/band-seats/room13-messages.jsonl (25 pages, 2,463 msgs; 109 text in the live log). Only human text message: the dispatch.
- Result repo HEAD 7d85854 (14 commits), main clean. Accepted: stage 1 = 9eda30d. Stage 2 reached, not accepted (CAND 3 481c4e3 rejected; 7d85854 unnominated). Implementer worktrees left on VM: ~/band-work/impl-1124-0510-s1 (9eda30d), impl-1124-0536-s2 (4655e23), impl-1124-0548-s2-live (752d054), impl-s2-0602-r29 (7d85854) — rotate before run 14.

## Post-run (post13.sh, 22:10:30–22:16:44 PST)
- Isolated harness on final HEAD 7d85854, --stage 2: completed, isolated, revision 7d85854, claimed 2; stage 1 122/122 (auth 51, dossiers 60, sample 11), stage 2 12/12 (upgrade source stage-1), stage-3 probe fail (0/9) as expected; fabrications 0, leaks 0. checks/run13-final-head-s2, harness13-head-s2.out.
- Isolated harness on highest accepted 9eda30d (clean clone /tmp/run13-acc), --stage 1: completed, isolated, revision 9eda30d, claimed 1; 122/122; stage-2 probe fail as expected. checks/run13-accepted-s1, harness13-acc-s1.out.
- `harness check`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json) — expected (check13.out).
- ONE live runway.com build (live13.sh = live12.sh with checkout 9eda30d; stage-1 of the highest ACCEPTED stage; bridge; NIMBLE_BASE_URL=http://172.17.0.1:18443): 06:12:48–06:16:44 UTC (22:12:48–22:16:44 PST, ~3.9 min incl. build), ready, spent_units 76 (forwarder 69: 7 lite searches, 42 extracts incl. 5 extract 500, 1 research run 202 + 14 polls — research quota OK on the new key). Saved band-run-13/dossier-runway.com.json.
  - legal_name unknown — WRONG
  - hq_city "New York" (baike.baidu.com) — CORRECT lenient (strict "New York City" differs)
  - ceo "Interactive Telecommunications Program" (websets.exa.ai "after NYU Interactive Telecommunications Program; … co-founder/CEO") — WRONG (expected Cristóbal Valenzuela)
  - founded_year 2018 (corpdigest) — CORRECT
  - headcount_range "11-50" (tracxn "49 employees as of Oct 26") — WRONG (expected 201–500)
  - funding_total 887,000,000 (tracxn "$887M over 10 rounds") — CORRECT lenient (±5%: +3.2% vs $859.5M), WRONG strict
  - Score 3/6 lenient (HQ, founded, funding), 1/6 strict (founded). Run 12: 5/6 / 2; run 11: 4/6 / 3; run 10: 4/6 / 2; run 7 (same tracxn $887M + 11-50): 4/6 / 3.
- Cleanup: dossier-live13 removed; 0 containers; bridge/host/none only. Forwarder still up; tunnel 0 × 407.

## How the new rules behaved
1. Reviewer replays captures offline on both commits before spending a new live run to check a repeat: WORKED for reproducibility. Every live drop was settled by replay, never by a repeat build: V2 (Linear CEO, Vercel funding — "frozen Stage 1 selector returns Karri/$863M, 4655e23 returns Jori/$9.3B" on the same captures) and V3 (Vercel CEO — three captures, both selectors). Zero extra repeat builds (run 12 spent a 4th Mercury build and hit the 402). Each candidate got exactly one 3-build round (S1 CAND 1; S2 CAND 1 partial, 2, 3); S1 CAND 2 and none other reused live. Gap: the per-candidate fresh round still starts in background at CANDIDATE time, so on V3 the replay had already shown the regression (21:59:59) while ~220 units of fresh live were being spent.
2. Spec tester regression tests within ~5 min of a REJECT: WORKED — S1 1.3 min (routing regression was even in before the verdict, from the early blocking note), S2 R1 1.8 min, S2 R2 3.3 min (8-row table). Run 12: 6.3.
3. Spec tester load tests direct against stand-ins: no proxy-backlog flake this run (run 12's mixed-load accounting flake did not recur); not otherwise observable.
4. Flaky tests reported by name: EXERCISED once — 21:53:10 the GET 5-s timeout on fc916d9 was reported by test and log path, not retried; it was a real regression (PDF parsing) and got fixed before CANDIDATE 3.
Carried rules: CANDIDATE to coordinator + reviewer at once HELD (all 5); reviewer started without a request HELD; live set within ~10 min HELD (9.2 min; slower than run 12's 2.4 because the reviewer pulled SEC/DPA sources first, and the coordinator asked for an R29 qualification check); reviewer-only live HELD (implementer/spec tester/coordinator 0 units, implementer replayed captures offline); ruling -> table tests EXERCISED (S2 R31/R34 8-row table after the second ruling); post-ACCEPT spec tester moved straight to stage-2 wave 1 (TESTS READY 7.6 min after S2 open).

## Nimble accounting (forwarder band-run-13/nimble_fwd13.log = nimble_fwd7.log lines after 4247; unit model as runs 7–12)
| Seat / window | units (forwarder) | notes |
|---|---|---|
| Reviewer preflights (21:05, 21:24) | 2 | 1 lite search each (anonymous containers frosty_williamson / loving_fermat, matched to reviewer rollout docker runs) |
| Reviewer live S1 CAND 1 bb0aa9c (3 builds 21:11–21:16) | 214 | self-report 226; 3 research starts; 17 extract 500 + 2 504 refused |
| Reviewer S1 CAND 2 9eda30d | 0 | live reused (change could not affect live) |
| Reviewer live S2 CAND 1 fd7fe53 (21:33–21:35, killed mid-run) | 176 | 3 research starts; Vercel 78 u completed, 2 builds lost |
| Reviewer live S2 CAND 2 4655e23 (21:43–21:47) | 225 | self-report 240 |
| Reviewer live S2 CAND 3 481c4e3 (21:58–22:01) | 222 | self-report 240 |
| Implementer / spec tester / coordinator | 0 / 0 / 0 | |
| Hark final runway (dossier-live13) | 69 | service 76; 5 extract 500; research 202 OK |
| TOTAL through forwarder | 909 (seats 840 = reviewer 100%) | |
No 402 / 429 (n402 = 0); 12 research starts by seats + 1 final all accepted on the new key. Tunnel 0 × 407. Far under ~2,500. Hark made no research probe (GET /v2/agents only).

## Stage time table (min, from stage open)
| | kickoff | live set | TESTS w1 | CAND 1 | VERDICT 1 | TESTS UPD | CAND 2 | VERDICT 2 | CAND 3 | VERDICT 3 | end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 run 13 | 1.3 | 9.2 | 7.6 | 7.4 | REJECT 15.2 (review 7.8) | 16.5 (+1.3) | 16.7 (+1.5) | ACCEPT 20.0 (review 3.3) | – | – | ACCEPT 20.0 |
| S1 run 12 | 1.4 | 2.4 | 10.3 | 10.0 | REJECT 21.6 (11.6) | 28.0 (+6.3) | 32.2 (+10.6) | – | – | – | stopped 37.2 (402) |
| S1 run 10 | 1.7 | 8.5 | 9.2 | 10.3 | REJECT 20.4 | 22.4 | 25.9 | ACCEPT 34.0 | – | – | ACCEPT 34.0 |
| S2 run 13 (open 21:23:22) | 0 | 10.1 (kept) | 7.6 | 9.1 | REJECT 17.2 (8.1) | 18.9 (+1.8) | 20.0 (+2.8) | REJECT 27.0 (7.1) | 34.4 (+7.3) | REJECT 40.4 (6.1) | stopped 45.2 (45-min rule; fix 7d85854 at 43.7 not nominated) |
| S2 run 10 | – | – | – | 15.7 | REJECT 24.8 | – | 32.4 | REJECT 43.5 | – | – | stopped 45.0 |
Total run wall: 66.5 min (21:02:05–22:08:34). Stage 1 ACCEPT at 20.0 min is the fastest ever (run 10: 34.0).

Reject reasons: S1 V1 bb0aa9c — R5 unmatched paths / unsupported methods 401 instead of structured 404/405 (after the R5 ruling); R5/R25/R27 imports with 1e309 / nested -1e999 -> 500 text/plain. S2 V1 fd7fe53 — R31/R34 render refusal kept static-only search values (1993, Anchorage) as candidates; R8/R38 HTML evidence route 200 for invalid domains. S2 V2 4655e23 — R31/R34/R29 Linear CEO "Jori Lallo" from an excerpt whose company match is only in an invisible image URL (+ headcount/funding variants in link destinations); reproduced offline. S2 V3 481c4e3 — R29 Vercel CEO "Benjamin Netanyahu" from a photo-caption headline after the visibility fix dropped the Markdown-split Rauch byline; reproduced on 3 captures.

## Bottlenecks
1. Stage 2 evidence selection churn: each fix to R31/R34 visibility moved a live field elsewhere (V2 Linear CEO, V3 Vercel CEO). The implementer had all prior captures but only replayed the cases named in the verdict; a whole-capture field-by-field diff against the previous selector would have caught both regressions before nomination.
2. Post-REJECT nomination in S2 R2/R3: TESTS UPDATED on an exact revision gated CANDIDATE; the implementer moved the commit (fc916d9 -> 481c4e3) and the tester re-ran, the coordinator relayed twice — 7.3 min from REJECT to CANDIDATE 3, and after V3 the fix (43.7 min) missed the 45-min mark because it was again waiting on a targeted test.
3. Reviewer stage-2 review stack killed at 21:34 (cause not established) — lost 2 of 3 live builds on S2 CAND 1.
4. Each live round ~220–240 units for 6–9 verified values; the round runs even when an offline replay has already settled the verdict (V3).

## Next generic tweaks (proposal, not applied)
- Implementer: before nominating a change to evidence selection, replay every captured live response from the phase on the previous accepted/nominated commit and on the fix, and list each selected-field change; an unexplained change is fixed first.
- Implementer/coordinator: after a REJECT, nominate as soon as your own run of the current suite passes on the exact revision; the spec tester's new regression tests may arrive during review and the reviewer runs them (don't hold CANDIDATE for TESTS UPDATED).
- Reviewer: on later rounds, run the offline replay of all earlier captures first; start the fresh live round only if the replay passes (a replay that reproduces a blocking drop already decides the verdict).
- Reviewer: name live-run containers distinctly and keep cleanup traps scoped to the probe's own container names (protects in-flight live builds).
- Spec tester: after a live regression verdict, turn each captured company page set into an offline field-by-field regression case (expected value per field), so later fixes can't silently move other fields.
- Operator: rotate the four ~/band-work/impl-* worktrees before run 14; restart handle = default-7f5ae855-… (listed again).

## Submission note
Run 13 ran factory-v2 51ed20d (= band-run-13/*.md). Stage 1 ACCEPTED at 9eda30d (20.0 min); stage 2 reached, not accepted (3 REJECTs; stopped at 45.2 min). Nothing pushed/merged/submitted.

## Left running / state
VM up; sandbox tunnel13.py (fresh 20:58:59, log band-run-13/tunnel.log, 0 × 407); VM iptables DROP tcp:22 from 35.162.191.92 and 35.162.213.8 (unchanged); VM forwarder nimble_fwd7.py pid 465923 (new key injected upstream; GET /v2/agents 200). Seats Stopped (agents + records kept); room-13 sessions interrupted + detached; inboxes empty; restart handle default-7f5ae855-… listed on all 4. 0 containers, no extra networks. ~/band-work/result (HEAD 7d85854), checks, dossier-stage-{1,2}-handoff.md, impl-* worktrees left in place for run 13 (rotate to -run13 before run 14). Recording ~/recording/factory-run-13.mkv. Run 14+ needs fresh approval.

## Files (band-run-13/)
coordinator/implementer/reviewer/spec-tester.md (mandates), dispatch.txt, tunnel13.py + tunnel.log, logger13.py, v13.py, exp13.py, units13.py, mon.sh, m2.sh, post13.sh, live13.sh, room13-log.jsonl (live log, first-seen PST), room13-messages.jsonl (export), docker-events13.log, nimble_fwd13.log, result/ (repo, HEAD 7d85854), checks/ (seat checks + reviewer reports + handoffs/ + hark-post/ + run13-final-head-s2/ + run13-accepted-s1/), harness13-head-s2.out, harness13-acc-s1.out, check13.out, post13.out, live13.out, live13-docker.log, dossier-runway.com.json, shot-pre.png.
