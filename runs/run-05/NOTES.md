# Band run 5 (Dossier, 4 seats) — notes

Started 2026-11-23 02:33 PST. Mandates work/band-dossier factory-v2 22c9e02 (local only, on top of 31f0b9d; not pushed). Exact mandate copies: work/band-run-5/{coordinator,implementer,reviewer,spec-tester}.md (sha256 identical on VM ~/band-seats/mandates5/). Vocab scan (band-run-4/vocabscan.py): 0 hits in 4 mandates + dispatch.

## Mandate changes in 22c9e02 (generic)
- Coordinator: spec pasted once per phase as a single message set mentioning every seat (not per seat); any ruling that changes what is blocking goes to every seat, implementer included, in one message; review request gated on the spec tester's first-wave suite.
- Implementer: post a candidate as soon as every blocking finding is fixed and the current suite passes; quality work beyond blocking items goes to the next round; skip optional slow suite variants before the first candidate.
- Reviewer: a live finding is blocking only when it breaks a ledger item as written, else carried (parallel live builds from candidate 1 and rerun-only-if-affects-live kept).
- Spec tester: two waves — wave 1 core suite, one test per ledger ID, ~10 min; wave 2 edges/faults/replays; first candidate waits only on wave 1. TESTS READY <phase> wave <n> <path>.
- Dispatch (band-run-5/dispatch.txt): run-4 dispatch with the paste line replaced by "The full text is pasted once per stage to the whole room; handoffs carry the task path, the spec path and the ledger." Rest identical.

## Setup (PST)
- Instructions set for all 4 seats from ~/band-seats/mandates5/; `show --reveal --json` == file for all 4 (3642/4430/3768/2232 chars).
- Detached run-4 host session default-b321b008-… from all 4 seats (detach removes the record). `band restart --host-session default-b321b008-…` then failed "peer not found" (setup loop 1). Worked as in run 4: `band restart --as <seat> --host-session default-caa7ba06-…` (run-2 session) for coordinator/implementer/reviewer; spec tester plain restart. All Connected, inboxes empty.
- ~/band-work/result -> result-run4 (HEAD 5b36475), checks -> checks-run4 (+ run-4 handoff file dossier-stage-1-handoff.md moved in); new empty result (git init -b main, local identity Factory <factory@factory.example.test>) and checks. No containers, no df- networks.
- Room 5341188d-6869-4c1e-8e3c-58a0e736dd68 "Factory run 5": `band chat new --as coordinator --with implementer --with reviewer --with spec-tester`; human 95a3f256-… added via `band chat add`; `band room rename`. 5 participants; each seat bound session default-5341188d-….
- Desktop switched to Factory run 5 (xdotool click 313,122), xscreensaver killed, xset s off.
- ffmpeg x11grab 2 fps libx264 ultrafast -> ~/recording/factory-run-5.mkv (pid 268085, 02:35:5x).
- Monitor: ~/band-seats/logger5.py (pid 268084) -> ~/band-seats/room5-log.jsonl; v5.py, exp5.py, live5.sh.
- Relay: sandbox tunnel.py pid 2244 up; VM 18443 GET /v2/agents -> 200.
- DISPATCH 02:36:14 PST, `band room send … --mention <coordinator id>`, text = run5/dispatch.txt. No other human messages.
- Stage 1 35-min deadline: 03:11:14 PST.

## Timeline (PST)
- 02:36:28 dispatch seen in room. 02:37:29 coordinator posts the spec ONCE to the whole room: 8 parts mentioning implementer + spec tester + reviewer, 33,391 chars (run 4: 24 parts / 100,017 chars). 02:37:44 three per-seat cards (851/814/908 chars, handoff ~/band-work/checks/stage-1-handoff.md, ledger R1–R23). 02:37:59 status to human. Kickoff 1.5 min.
- 02:39:54 first implementer commit aab08c4; 02:43 b44ca91, 79e7416.
- 02:44:33 TESTS READY Stage 1 wave 1 (10 tests, mock Nimble) to implementer + coordinator — 8.3 min (run 4: 14.6; run 3: 10.2).
- 02:45:49 CANDIDATE 1 79e7416 (1,729 chars; wave 1 10/10) — 9.6 min after dispatch (run 3: 11.0; run 4: 19.1). 02:46:04 coordinator review request (709 chars, paths only).
- 02:47:20 reviewer independent checks ready (to coordinator 416 + probe list to implementer 357). 02:49:06 reviewer asks spec tester for official sources; 02:50:06 spec tester answers (2,447 chars).
- Reviewer live builds: first attempts (dirs -client/-network/-retry/-configured/-final, 02:47–02:53) failed in <1 s with 0 units — the candidate container never reached the relay. Only the "-host-provider" variant reached it: relay traffic 02:53–02:57 (Cloudflare 70 units, Mercury 80 units; ready in 165 s / 177 s). ~6 min of review lost to the live route.
- Findings sent straight to implementer before verdict: R22 02:50:22 (fixed 02:51:22), R17 02:52:23 (fixed 02:54:24), R16 02:55:25, R5 02:56:25 (both fixed 02:57:41–56), R18–R20 live 02:58:11, R21 02:59:12 (fixed 03:00:43–58, after verdict).
- 02:59:58 VERDICT 1 79e7416 REJECT (2,823 chars) to implementer + spec tester + coordinator in one message. 23.7 min; review 14.2 min (run 4: 6.8). Isolated harness 122/122 claimed 1; wave 1 10/10; independent 9/14. Blocking: R5 sub-microsecond clock order; R16 transient refusal of the exact-domain search then budget spent with zero exact searches; R17 CEO sentence in search text discarded when extract returned no page + last exact retry URL never extracted; R18–R20 live headcount cited from a link destination (Cloudflare founding sentence; Mercury satisfaction link); R21 unanswered extract deadlines charged 0 units (cap exceeded under §9); R22 import of www.www.-normalized domain -> 422. Carried: cumulative funding figures not corroborated by official material.
- 03:00:13 / 03:00:28 coordinator repair cards to implementer (600) and spec tester (460). No blocking-scope ruling was needed this run.
- 03:01:13 implementer fast-forwards main to a88a486 (all blocking fixed, 9 regressions). 03:03:15 TESTS UPDATED (17 groups; 3.3 min after verdict; run 4: 2.0).
- 03:04:15 CANDIDATE 1 (round 2) a88a486 (2,287 chars; updated wave 1 17/17) — 28.0 min; 4.3 min after REJECT (run 4: never posted). 03:04:30 review request (843).
- 03:07:32 reviewer -> implementer two blocking cases. 03:08:18 VERDICT 1 a88a486 REJECT (1,954 chars) — 32.1 min; review 3.8 min (run 3 round 2: 9.1). Isolated 122/122; wave 1 17/17; independent 16/18; no new paid live calls (correctly skipped). Blocking: R16 two transient 500s on the exact query -> no third attempt, 80 units, zero exact searches; R18–R20 Markdown link TITLE punctuation exposes an identifier ("7025113. More information" -> 10001+). Verified R5/R17/R21/R22.
- 03:08:48 coordinator round-3 cards (spec tester 403, implementer 527). 03:09:49 TESTS UPDATED (19 groups). 03:09:52 b39082a (R16 bounded retry window), 03:10:25 857f68a (R18–R20 link masking) — never posted as candidate.
- 03:11:14 Stage 1 hit 35 min without ACCEPT -> STOP. 03:11:17–22 `band stop` all 4 (agent + record kept), ffmpeg SIGINT -> ~/recording/factory-run-5.mkv (35.9 MB). No room messages sent. R16 rejected twice (different fault counts), not 3x; no stall.

## Post-stop artifacts (PST)
- Isolated harness on HEAD 857f68a (clean tree): state completed, mode isolated, claimed stage 1, stage 1 122/122, stage-2 probe 0/12 (expected). VM ~/band-work/checks/run5-final-s1/report.json (copy band-run-5/checks/run5-final-s1/).
- `harness check --track dossier <repo>` (positional repo; post4.sh's `--repo` form errors): 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json missing) — expected for an unpackaged run repo.
- Live runway.com @857f68a via relay (11:13:07–11:14:42 UTC, ~95 s): ready, 40 units. legal_name "RUNWAY OWNER, LLC" WRONG (LEI-directory namesake; correct Runway AI, Inc.); hq_city "New York" CORRECT; ceo "Cristóbal Valenzuela" CORRECT (summit.runway.com, first time right in any run); founded_year 2018 CORRECT; headcount_range 51-200 WRONG source (LeadIQ page about a different Runway, SF finance software); funding_total 859,500,000 CORRECT (getlatka $859.5M). 4/6 (4/5 graded truth fields). File band-run-5/dossier-runway.com.json.
- Room export band-run-5/room-messages.jsonl (1,237 msgs: 49 text, 515 tool_call, 507 tool_result, 131 task, 31 thought). Text chars: coordinator 39.9k (33.4k = one 8-part spec paste), implementer 10.5k, reviewer 10.1k, spec tester 5.8k. Monitor log band-run-5/room5-log.jsonl (first-seen times).
- Result repo copy band-run-5/result (HEAD 857f68a, branch stage1-r22 also present). Handoff file, spec-tester suite, review plan, s1-1/s1-2 harness reports: band-run-5/checks/.
- Containers and df-/dossier networks removed; no codex/ffmpeg/logger processes. VM left running. Nothing pushed. Rooms 1–4 untouched.
- Nimble (relay log): reviewer live 150 units (Cloudflare 70, Mercury 80, 02:53–02:57) + final runway 40 = 190 metered. Implementer and spec tester made 0 relay calls (mock only). No credit/quota errors; 16 extract 500s were target-page failures.

## Stage 1 time breakdown (min from dispatch 02:36:14)
kickoff 1.5 | TESTS READY w1 8.3 | CANDIDATE 9.6 | review 14.2 (first blocking finding +4.3 in) -> REJECT 23.7 | fixes all committed before/at verdict+1.3 | TESTS UPDATED 27.0 | CANDIDATE 28.0 | review 3.8 -> REJECT 32.1 | fixes committed 33.6/34.2 | stop 35.1.
Run 4: CANDIDATE 19.1, REJECT 26.2, stop 35.1. Run 3: CANDIDATE 11.0, REJECT 18.0, CANDIDATE 24.1, REJECT 33.7, stop 35.0. Run 2: CANDIDATE 14.6, REJECT 26.9, CAND 38.0, REJECT 45.6, CAND 51.2, ACCEPT 56.5 (S2 50.3).

## Bottlenecks
1. Review round 1 = 14.2 min: ~6 min lost getting the candidate container to reach the live provider (5 failed live attempts before the host-provider route worked), and six blocking findings arrived one by one.
2. Narrow fixes -> same class rejected again: R16 (one refusal -> two refusals) and R18–R20 (link destination -> link title). Round 2 found neighbours of round-1 findings.
3. Spec tester wave 1 (10 tests) caught none of the 6 round-1 blockers; all came from reviewer probes. Its value showed only as regression gating.

## Next generic tweaks (proposal, not applied)
- Reviewer: preflight the live route during prep (one cheap call from inside a container on the default bridge) so live builds start the moment the candidate lands.
- Reviewer + implementer: treat each blocking finding as a class — reviewer probes at least one neighbouring variant before the verdict; implementer fixes the class and adds a regression for a neighbouring variant.
- Spec tester wave 1: include one transient-fault case (repeated, not single) for each mandatory outside call and one marked-up-text case per extracted field, still ≤10 min.

## Submission note
Final submission mandates must match what actually ran. Run 5 ran factory-v2 22c9e02 (= band-run-5/*.md); run 4 = 31f0b9d, run 3 = dcd02a4, run 2 = b2f6bca. The repo's mandates/ folder must be set to the commit of the run that is submitted.
