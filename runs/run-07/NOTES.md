# Band run 7 (Dossier, 4 seats) — notes

Started 2026-11-23 11:09 PST. Mandates work/band-dossier factory-v2 0adc4c0 (local only, on top of e104885; not pushed). Exact mandate copies: work/band-run-7/{coordinator,implementer,reviewer,spec-tester}.md (sha256 identical on VM ~/band-seats/mandates7/; 3909/5067/4704/2395 chars). Vocab scan (band-run-4/vocabscan.py): 0 hits in 4 mandates + dispatch. Dispatch = band-run-6/dispatch.txt byte-identical (sha256 bf3a1e22…), VM copy ~/band-seats/run7-dispatch.txt.

## Mandate changes in 0adc4c0 (generic)
- Implementer: one realistic live build per candidate with the service address exactly as given; compare correct outputs with the previous candidate; behaviour must not depend on host name.
- Reviewer: a drop in correct live outputs vs previous candidate / last accepted phase is blocking; use the address as given (no alias); reuse live results when the change can't affect them.
- Coordinator: state live gates up front in the ledger.

## Setup (PST)
- Sandbox tunnel.py (band-run-1) still running (pid 2538 since run 6). VM up 14h, same IP 35.252.223.41, disk 12% (128G free).
- ~/band-work rotation (nothing deleted): run-6 fix worktrees `git worktree move` -> dossier-stage-1-fixes-run6, dossier-stage-2-fixes-run6; result -> result-run6 (HEAD 83a4cce), checks -> checks-run6; `git worktree repair` in result-run6 (all 4 worktrees listed OK). New empty result (git init -b main, Factory <factory@factory.example.test>) and checks.
- Instructions set (`band agent instructions set --instructions-stdin`) for all 4 seats from ~/band-seats/mandates7/; `show --reveal --json` instructions.content == file for all 4 (3909/5067/4704/2395).
- Detached run-6 host session default-5a38f7fe-… from all 4 seats (room 6 kept). Restart: coordinator/implementer/reviewer `--host-session default-caa7ba06-…`, spec tester `--host-session default-c80c81bf-…`, first try (no loop). All Connected.
- Room 7eb89d0c-8317-4259-bfad-a5a956e5d2ab "Factory run 7": `band chat new --as coordinator --with implementer --with reviewer --with spec-tester`; human 95a3f256-… added via `band chat add`; `band room rename`. 5 participants; each seat has session default-7eb89d0c-….
- Seat env (from /proc of the 4 codex processes): NIMBLE_BASE_URL=http://127.0.0.1:18443, NIMBLE_API_KEY set (placeholder; real key injected on the wire by the sandbox proxy), GIT_AUTHOR_NAME per seat.
- 11:12 PST: Frank switched the Nimble key (new vault id ab63bc73…, old fc3b42ae removed; sandbox proxy injects automatically). tunnel.py does not reference the vault id; GET /v2/agents 200 from VM host and container after the switch.
- Forwarder: replaced nimble_fwd.py (pid 4270, killed) with ~/band-seats/nimble_fwd7.py (same forwarding; adds per-request attribution: host clients -> seat via owning process GIT_AUTHOR_NAME, container clients -> container name; logs cost-relevant body fields only (search_depth, nurls, render…), never headers) -> ~/band-seats/nimble_fwd7.log. Two small fixes to my own logger (port hex, patch assert; one accidental self-kill via pkill -f, restarted). Final pid 463183 from 11:15:35. Verified 200 from host (who=seat:TestHost) and container (who=ctr:fwdtest).
- Desktop switched to Factory run 7 (xdotool click 313,116), xscreensaver killed, xset s off -dpms.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-7.mkv (pid 461657, 11:12:5x PST), log ~/recording/ffmpeg-run7.log.
- Monitor: ~/band-seats/logger7.py (pid 461658) -> ~/band-seats/room7-log.jsonl; v7.py, exp7.py.
- DISPATCH 11:15:46 PST (epoch 1795461346), `band room send <room> "$(cat run7-dispatch.txt)" --mention <coordinator fda466af-…>`. No other human messages.
- Stop rules: stage >45 min wall without ACCEPT (stage 1 deadline 12:00:46 PST); same reject 3x; stall >20 min; Nimble credit/quota errors; total Nimble units this run > ~2,000.

## Timeline (PST)
- (incident, infra) 11:50:25–11:52:04 PST live route down: sandbox upstream proxy started answering CONNECT with 407 Proxy Authentication Required (proxy credentials held by the long-running tunnel.py from run 6 went stale). 34 forwarder calls ERR (OSError -> 502 to clients), incl. implementer's post-REJECT live builds (Stripe/OpenAI/Cloudflare "failed") and its probe. Restarted band-run-1/tunnel.py with current env (new pid 18494, log band-run-7/tunnel.log) 11:51:58; 200 from VM host and container 11:52:06. No room message sent. Not a Nimble credit/quota error.
- 11:15:56 dispatch seen. 11:16:57–11:17:12 coordinator spec pasted once to the room in 7 parts (~33k) + stage-1 cards to all three seats (552–668 chars), handoff ~/band-work/dossier-stage-1-handoff.md, ledger R1–R20 (R20 = live gate: "measured live Nimble baseline", correct cited fields per domain, comparable repeat). Kickoff 1.4 min. 11:17:27 status to human.
- 11:18:28 implementer picks stripe.com + openai.com for R20 and "pass the supplied Nimble address unchanged"; 11:18:43 coordinator records both in handoff (live gate stated up front: NEW, worked).
- 11:19:28 reviewer prep + live-route preflight OK (1 lite search, 1.64 s). Reviewer: "The supplied endpoint is host loopback, so the live container uses host networking to preserve that exact address" (implementer did the same: all seat live containers ran --network host with NIMBLE_BASE_URL=http://127.0.0.1:18443).
- 11:24:47 TESTS READY Stage 1 wave 1: 21 checks (run 6: 30) — 9.0 min (run 6: 7.2).
- Implementer live self-check loop BEFORE candidate 1: live containers 19:17, 19:27, 19:30, 19:35, 19:38 UTC (5 rounds of Stripe/OpenAI builds), 418 units. Commits 646715b, be91961 (19:23), 836a1c2 (19:27), 9eb4eb1 (19:30), b0ab35e (19:35), ad9d56a (19:37). What it caught: (a) live export 500 on a WebRouter timestamp object in research metadata (same class as run-6 S1 REJECT R19) — fixed before candidate; (b) a partner company's CEO and a stale employee count (live attribution errors) — fixed; (c) mock refusal fallback asking for snippets (from wave 1, 20/21 -> 21/21).
- 11:41:58 CANDIDATE 1 ad9d56a (2,005; w1 21/21 in 35.8 s) — 26.2 min (run 6: 12.0). Live baseline: stripe.com 6/6 in 30.9 s / 34 units; openai.com 3/6 in 142.4 s / 76 units (legal name unknown, $11B single-installment funding not credited) = 9/12 at 110 units. Live export 3.4 MB round-tripped unchanged.
- 11:42:28 review request. Findings to implementer before verdict: 11:44:29 R14 blocking (sole Appendix-A value dropped by an extra relevance veto: 4 mock variants -> unknown; introduced by the live-tuning commits); 11:45:15 R5 (sub-microsecond backwards clock 204 instead of 422, precision truncated; 2 variants); 11:45:45 live Cloudflare CEO = "The Daily Stormer" + headcount below 10-K; 11:48:32 class variant Apple CEO stale (Tim Cook after Ternus handover).
- 11:49:02 VERDICT 1 ad9d56a REJECT (2,354) — 33.3 min; review 6.6 min. Harness isolated 122/122 claim 1, independent w1 21/21. Blocking R5, R14, "live R20" (Apple 159 s/64 units 4/6; Cloudflare 135 s/80 units 2/6 — reviewer used different domains than the implementer, so no comparable previous-candidate baseline).
- 11:49:32 coordinator ruling to all seats: REJECT stands on R5 + R14; new-domain live scores = comparison data; semantic/freshness live issues earn zero credit and carry; only a reproducible drop on a comparable repeat blocks R20.
- 11:51:03 TESTS UPDATED (24 checks; 3 regressions reproduce on ad9d56a) — 2.0 min after verdict.
- 11:50:25–11:52:04 live route outage (proxy 407, see setup incident); implementer's 3 post-verdict live builds failed at 0 units, 11:51:33 coordinator: candidate may go with live rerun pending.
- Fixes in separate worktree ~/band-work/stage1-r14-1944 (branch fix/stage1-evidence): 587c24e (R14), b9a0c11 (R5), e502b0d, 9738115, 609dc56 (CEO/headcount ranking). Live containers r14-e502 (outage), 9738115, 609dc56.
- 11:58:53 implementer "isolated fix ready" 609dc56 (w1 24/24, 9 local + 7 reviewer reproductions; Stripe 6/6 and OpenAI 3/6 preserved on intermediate live runs; Cloudflare replay picks Matthew Prince + 5001–10000) — 43.1 min. 11:59:23 coordinator fast-forwards shared checkout, REVIEW 1 609dc56 (round 2) — 43.6 min. Reviewer started isolated harness s1-2 + live Apple/Cloudflare; implementer exact-SHA live Stripe/OpenAI running in parallel.
- 12:00:46 45-min stage limit reached without ACCEPT -> STOP. Stage 1 NOT accepted (round-2 review in progress).

## End (PST)
- 12:00:52 `band stop` all 4 (agent + record kept). 12:00:5x ffmpeg SIGINT -> ~/recording/factory-run-7.mkv (44.6 MB, "Exiting normally"). No room messages sent by me besides the dispatch.
- Room export ~/band-seats/room7-messages.jsonl (12 pages, 1,141 msgs) -> band-run-7/room-messages.jsonl; monitor log -> band-run-7/room7-log.jsonl; text-only digest band-run-7/texts.md. Logger + docker-events logger stopped.
- Message mix: 39 text, 482 tool_call, 472 tool_result, 117 task, 27 thought. Text chars: coordinator 39.0k (~33k spec paste), reviewer 5.8k, implementer 5.7k, spec tester 3.8k, human 2.7k.
- Containers at stop (reviewer r2 live/mock, harness svc/web, implementer 609dc56 live): logs saved to checks/hark-final-container-logs/, all removed; df-run-* network removed.
- Handoff copied to checks/handoffs/; reviewer /tmp evidence (dossier-review-live1-ShwwXi, dossier-review-round2-vNMogh) copied to checks/reviewer-tmp/. Implementer worktree moved (git worktree move) to ~/band-work/stage1-r14-1944-run7.
- Isolated harness on final HEAD 609dc56 (stage 1 — highest stage reached; NOT accepted): state completed, mode isolated, claimed 1, 122/122 (checks/run7-final-s1/, harness7.out). Reviewer's r1 harness on ad9d56a also 122/122 claim 1 (checks/s1-1).
- `harness check`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json) — expected (check7.out).
- Live runway.com (live7.sh: stage-1 @609dc56, bridge network, NIMBLE_BASE_URL=http://172.17.0.1:18443 exactly as the dispatch gives it for containers, no --add-host alias): 20:04:20–20:07:56 UTC (12:04:20–12:07:56 PST, 216 s), ready, spent_units 78. Saved band-run-7/dossier-runway.com.json. Not all-unknown -> no aliased attempt needed. The service ran fully live on a non-sdk host (run-6 test-mode trap absent).
  - legal_name unknown — MISS
  - hq_city "New York City" (highperformr.ai) — CORRECT
  - ceo "Cristóbal Valenzuela" (felicis.com interview) — CORRECT
  - founded_year 2018 (corpdigest) — CORRECT
  - headcount_range "11-50" (Tracxn "49 employees as of Oct 26") — WRONG (truth 201-500; stale/aggregator)
  - funding_total 887,000,000 (Tracxn "total funding of $887M over 10 rounds") — vs truth ~$859.5M: cumulative figure, +3.2% — CLOSE (correct if ±5% tolerance; wrong if exact)
  - Score 4/6 with funding tolerance (3/6 strict). Run 6: 1/6 (stage 4, aliased). Run 5: 4/6 (stage 1). Note stage 1 here vs stage 4 in run 6 (stage-2+ evidence rules not present).

## Nimble accounting (forwarder nimble_fwd7.log, attributed; attr7.py)
Units = spec §9 model on calls the provider answered 2xx (search lite 1, extract 1/URL, research start 25; 'standard' depth counted 1). Failed extracts (500, 140 total) counted 0 here; the app's own spent_units charges them (so app-reported figures run ~15–25% higher). Calls during the 407 outage never reached Nimble.
| Seat / window | units |
|---|---|
| Implementer pre-candidate-1 self-checks (5 live rounds) | 418 |
| Reviewer preflight | 1 |
| Reviewer review 1 (Apple + Cloudflare) | 118 (reviewer-reported 144 incl. failed extracts) |
| Implementer fix window (live after REJECT) | 188 |
| Round 2 (implementer 609dc56 + reviewer r2 live in parallel, host network so not separable) | 14 impl + 152 overlap |
| Spec tester / coordinator | 0 (mock only) |
| Hark final runway | 59 (app-reported 78) |
| TOTAL | 950 (~1,100 under the app's accounting) — under the 2,000 stop limit |
Implementer total ≈ 620 + share of 152 (≈ 700); reviewer ≈ 119 + share (≈ 195). Implementer live use (new this run) was ~3.5x the reviewer's. No credit/quota errors.

## Stage time table (min, from dispatch 11:15:46)
| | kickoff | TESTS w1 | CAND 1 | VERDICT 1 | TESTS UPD | CAND 2 | verdict 2 | ACCEPT |
|---|---|---|---|---|---|---|---|---|
| S1 run 7 | 1.4 | 9.0 | 26.2 | REJECT 33.3 (review 6.6) | 35.3 | 43.1 (review req 43.6) | stopped at 45.0 | – |
| S1 run 6 | 1.4 | 7.2 | 12.0 | REJECT 22.6 (review 10.4) | 24.1 | 26.2 | ACCEPT | 32.5 |

## Bottlenecks
1. Implementer live self-check became a live-tuning loop: 5 live rounds (418 units) before candidate 1, candidate at 26.2 min vs 12.0 in run 6. The ledger's R20 ("measured live baseline" + correct cited fields) invited optimizing live scores instead of one smoke build.
2. Live tuning overfit and broke the spec: the relevance veto added for live attribution dropped sole Appendix-A values (R14 blocker). Wave-1 (21 checks) didn't cover it; reviewer variants did.
3. Implementer and reviewer used different live domains (Stripe/OpenAI vs Apple/Cloudflare), so the new "drop vs previous candidate" rule had no comparable baseline; the reviewer raised new-domain live findings as blocking and the coordinator had to narrow it (ruling).
4. Infra: sandbox proxy credentials went stale mid-run (407, ~100 s); cost the implementer one live round. Host-network live containers make per-seat attribution need timing correlation.
5. Wave 1 still caught none of the round-1 blockers (R5 sub-microsecond, R14 sole value) — same as run 6.

## Next generic tweaks (proposal, not applied)
- Implementer: the per-candidate live build is a smoke check, not a tuning loop: at most one live build pair per candidate, time-boxed (~5 min); live-only improvements go into the next round unless a ledger item fails. After any live-motivated change, rerun wave 1 + marked-up-text tests and check that every value the spec admits as sole evidence still comes out known (live tuning must never narrow what the spec accepts).
- Coordinator: fix one shared live domain set in the ledger at kickoff for both implementer and reviewer (comparable repeats); reviewer may add one exploratory domain whose findings carry, never block.
- Reviewer: live blocking only on a drop on the shared domains vs previous candidate / last accepted phase; reuse the implementer's exact-SHA live results when they are on the shared set and the reviewer's spot check agrees.
- Coordinator: first candidate target ~15 min; a candidate that passes wave 1 goes to review even if live quality work is pending.
- Spec tester: wave 1 add one "sole compliant value survives" test per extracted field (catches over-filtering).

## Submission note
Run 7 ran factory-v2 0adc4c0 (= band-run-7/*.md). No stage accepted within 45 min; best full run remains run 6 (e104885). Nothing pushed/merged/submitted.

## Left running / state
VM up; sandbox tunnel.py pid 18494 (restarted this run, log band-run-7/tunnel.log); VM forwarder nimble_fwd7.py (attribution version) up on 127.0.0.1/172.17.0.1:18443; seats stopped (agents + records kept); no containers, no extra networks; ~/band-work/result and checks left in place for run 7 (rotate to -run7 before run 8; also stage1-r14-1944-run7 worktree).
