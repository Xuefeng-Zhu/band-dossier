# Band run 8 (Dossier, 4 seats) — notes

Started 2026-11-23 14:03 PST. Mandates work/band-dossier factory-v2 1c07674 (local only, on top of 0adc4c0; not pushed). Exact mandate copies: work/band-run-8/{coordinator,implementer,reviewer,spec-tester}.md (sha256 identical on VM ~/band-seats/mandates8/; 4506/5765/5121/2509 chars). Vocab scan (band-run-4/vocabscan.py): 0 hits in 4 mandates + dispatch. Dispatch = band-run-6/dispatch.txt byte-identical (sha256 bf3a1e22…), VM copy ~/band-seats/run8-dispatch.txt.

## Mandate changes in 1c07674 (generic)
- Coordinator: at phase 1 the reviewer proposes and the coordinator fixes a shared live set in the ledger (3 well-documented subjects, one with namesakes, expected outputs independently checked, never an example named in the requirements); implementer and reviewer both measure on it every phase. Live gate default = drop on the shared set is blocking; spend per correct output carried. First candidate target ~15 min; a commit passing wave 1 goes to review even if live work is pending.
- Implementer: run the shared set once per candidate (~5 min, background), address as given; no live tuning loop; live-only improvements wait for the next round. Gathering rules: own site first, one targeted query per missing output, keep link/heading/caption text as labelled weaker candidates, namesake = source not on/linking the subject's site, a part never beats a whole/total.
- Reviewer: proposes the shared set at phase 1; live blocking only on breaking a ledger item or a drop on the shared set; other live inputs exploratory/carried.
- Spec tester: wave 1 adds one single-source output test per extracted field (sole valid source must still come out).

## Setup (PST)
- Sandbox had restarted (no tunnel, no paramiko). pip install paramiko; started band-run-1/tunnel.py FRESH (setsid, log band-run-8/tunnel.log) 14:04:14 — fresh proxy credentials (the sandbox proxy token in this env expires ~17:04 PST; restart tunnel if 407s appear). VM up 16h55m, same IP 35.252.223.41, disk 13% (127G free).
- Forwarder ~/band-seats/nimble_fwd7.py (attribution version, pid 465923) still up; log continues in ~/band-seats/nimble_fwd7.log. GET /v2/agents 200 from VM host (127.0.0.1:18443) and from a container (fwdtest8 -> 172.17.0.1:18443) at 14:04:25.
- ~/band-work rotation (nothing deleted): result -> result-run7 (HEAD 609dc56), checks -> checks-run7; stray top-level ~/band-work/dossier-stage-1-handoff.md (identical to checks-run7/handoffs copy) moved to checks-run7/handoffs/dossier-stage-1-handoff.toplevel.md; worktree stage1-r14-1944-run7 already moved in run 7 (`git worktree repair` printed a ".git file broken" warning but `git -C stage1-r14-1944-run7 log` works, gitdir points at result-run7). New empty result (git init -b main, Factory <factory@factory.example.test>) and checks.
- Instructions set (`band agent instructions set --instructions-stdin`) from ~/band-seats/mandates8/; `show --reveal --json` instructions.content == file for all 4 (4506/5765/5121/2509).
- Detached run-7 host session default-7eb89d0c-… from all 4 seats (room 7 kept). Restart: coordinator/implementer/reviewer `--host-session default-caa7ba06-…`, spec tester `--host-session default-c80c81bf-…`, first try. All Connected.
- Room 89977895-1027-43e4-a5fe-f87eea30dc5f "Factory run 8": `band chat new --as coordinator --with implementer --with reviewer --with spec-tester`; human 95a3f256-… added via `band chat add`; `band room rename`. 5 participants; each seat has session default-89977895-….
- Desktop switched to Factory run 8 (xdotool click 313,116), xscreensaver killed, xset s off -dpms.
- ffmpeg x11grab 1600x1000 2 fps libx264 ultrafast -> ~/recording/factory-run-8.mkv (pid 496156, 14:06 PST), log ~/recording/ffmpeg-run8.log.
- Monitor: ~/band-seats/logger8.py (pid 496157) -> room8-log.jsonl; docker events -> docker-events8.log (pid 496158); v8.py, exp8.py, units8.py (since 22:06:15 UTC).
- DISPATCH 14:06:15 PST (22:06:15 UTC, epoch 1795471575), `band room send <room> "$(cat run8-dispatch.txt)" --mention <coordinator fda466af-…>`. No other human messages.
- Stop rules: stage >45 min wall without ACCEPT (stage 1 deadline 14:51:15 PST); same reject 3x; stall >20 min; Nimble credit/quota errors; total Nimble units this run > ~2,500.

## Timeline (PST)
- (incident, infra) STRAY RUN-7 SEATS RESUMED in room 7 (7eb89d0c) ~14:05–14:19 PST. Cause: run 7 had been stopped mid-turn (interrupted turns + queued room-7 messages); after `band detach` of the room-7 host session and `band restart --host-session <run-2/3 session>`, jamd re-spawned a room-7 runtime for every seat (8 codex app-servers instead of 4). The run-7 seats noticed the rotation and kept working on run-7 stage 1 in ~/band-work/result-run7 + checks-run7: new commits c866717 (R13/R14) and 7cb24e1 (R5) on fix/stage1-evidence, uncommitted edits in stage1-r14-1944-run7, checks-run7/s1-3, spec-tester TESTS UPDATED, reviewer live containers dossier-review-run7-resume-live(-b), -boundary, -r3-live/-r3-mock (images 609dc56/7cb24e1). Found 14:19 PST from container names; fixed 14:20 with `band runtime interrupt --as <seat> --host-session default-7eb89d0c-…` + `band detach` for all 4 seats: the 4 room-7 codex pids exited, room-8 sessions untouched (4 live pids). Removed the two still-running run-7 containers (logs -> checks-run7/hark-run8-stray-container-logs/). Run-7 records left as they are (not deleted; they now include these post-stop additions). Room 8 itself was not affected (result repo only has run-8 commits); the stray live calls share the uid0 attribution bucket, separated by container windows in the Nimble accounting. No room message sent. LESSON: before restarting seats for a new run, interrupt + detach any room whose turns were cut off, and check `pgrep codex` = 4 right after the first handoff.
- 14:06:21 dispatch seen. 14:07:52 coordinator spec pasted once to the room in 8 parts (~33k) + stage-1 card (part 1/8) to all three seats, handoff ~/band-work/dossier-stage-1-handoff-run8.md, ledger R1–R25 (R25 = live gate: reviewer fixes 3 subjects incl. a name collision, excluding the spec example; drop on the fixed set vs preceding measured candidate is blocking; spend/correct carried). Kickoff 1.6 min. Status to human 14:07:52.
- 14:09:38 SHARED LIVE SET fixed by the reviewer in the handoff (3.4 min after dispatch): apple.com (collision: Apple Corps), etsy.com, dropbox.com, with source-checked expected values (Apple Inc./Cupertino/John Ternus/1976/10001+; Etsy, Inc./Brooklyn/Kruti Patel Goyal/2005/1001-5000; Dropbox, Inc./San Francisco/Drew Houston or Ashraf Alkarmi co-CEOs/2007/1001-5000; funding explicitly "no comparable lifetime equity reference", reviewed per source). 14:10:39 reviewer live-route preflight OK (host networking, 1 lite search 6.54 s).
- Commits a83f46d (14:11), e11c5d7 (14:12), 2aba421 (14:14), f7c7fd4 (14:16).
- 14:13:41 TESTS READY 1 wave 1 (23 checks incl. six marked-up sole-source fields) — 7.4 min (run 6: 7.2, run 7: 9.0). 14:14:57 reviewer prep ready. 14:17:29 coordinator R6 ruling (GET on refresh path: any structured 4xx). 14:17:59 TESTS READY wave 2 (+ coordinator forwards an R5 fractional-clock finding on f7c7fd4 to the reviewer before review).
- Implementer live: an unreported pass on 2aba421 (container dossier-r8-impl-live 14:14:35–14:17:05, ~228 units by window) then the reported pass on f7c7fd4 (14:17–14:20:45): 8/18 correct, 207 units, 202 s.
- 14:22:17 CANDIDATE 1 f7c7fd4 (1,830; w1 23/23) — 16.0 min (run 6: 12.0, run 7: 26.2). 14:22:32 review request.
- Findings to implementer before verdict: 14:23:33 R5/R13 picosecond clock; 14:26:35 R19/R20 multi-sentence research citations + R22 import of invalid values. Fixes before verdict: fd21eeb (14:23, R5/R13), 69b589c (14:27, R19/R20/R22), spec tester independently confirmed fd21eeb 14:26.
- 14:28:51 VERDICT 1 f7c7fd4 REJECT (2,218) — 22.6 min; review 6.3 min. Harness isolated 122/122 claim 1 (86.8 s); w1 23/23; w2 6/7; independent 5/7. Blocking R5/R13 (2 variants), R19/R20 (period + exclamation variants), R22 (2 field variants). Reviewer live 10/18 at 185 units (Apple 3, Etsy 4, Dropbox 3); carried: headcount from links/addresses, 2010 URL over 1976 founding, campaign proceeds as funding.
- 14:30:37 TESTS UPDATED (1.8 min after verdict; wave 2 11 checks incl. Etsy live replay from reviewer capture). Implementer live on 69b589c 14:29–14:33 (8/18, 157 units) — candidate held ~3 min for it although the coordinator asked twice to submit while live ran (14:29:36, 14:30:52).
- 14:34:09 CANDIDATE 2 69b589c (2,255) — 27.9 min; 5.3 min after REJECT. 14:33:54 review request (coordinator sent it on the 14:33:39 receipt).
- 14:36:25 reviewer blocking: leap-second clock moves (R5) + uppercase-labelled research sentences discarded (R19/R20). 14:37:56 live fixed set 10/18 -> 9/18 (Etsy legal name unknown: this run's provider snippet spelled "ETSY, INC."; reviewer states "a code-caused change in live evidence was not established").
- 14:38:57 VERDICT 1 69b589c REJECT (2,343) — 32.7 min; review 5.0 min. Isolated 122/122 claim 1 (84.7 s); w1 23/23; w2 11/11; independent 7/9. Blocking R5 (RFC 3339 leap seconds UTC and −08:00 -> 422 instead of 204), R19/R20 (labelled prose), R25 (9/18 vs 10/18 — drop measured, cause not shown to be code).
- 14:39:27 coordinator: R5 and R19/R20 now have two REJECT rounds each; R25 target = recover reviewer 10/18 while holding implementer 8/18.
- Fixes efa1b03 (14:38, R5 leap seconds via IANA table + labelled prose) and 0778d05 (14:39, R19/R20/R25 weak-candidate confirmation, direct company-wide evidence first). 14:40:28 shared checkout clean at 0778d05. 14:40:43 TESTS UPDATED; 14:41:14 spec tester w2 13/13 on 0778d05 (both new regressions fail on 69b589c). Implementer live on 0778d05 started 14:39:59.
- 14:40:21 / 14:41:05 / 14:41:14 Nimble POST /v2/agents/runs -> 402 (3x). Hark probe from the sandbox (POST /v2/agents/runs, dummy agent, no charge): HTTP 402 `billing_not_allowed`, "This account cannot be billed for a Web Search Agent run", block_reason `trialNoQuota`. Search/extract still 200. = Nimble credit/quota error -> STOP RULE.
- 14:42:04–05 `band stop` all 4 (agent + record kept) — 35.8 min after dispatch. Stage 1 NOT accepted; CANDIDATE 3 (0778d05) was being prepared (wave 1/2 green, live pass in progress), never reviewed. Max same-reject count reached 2 (R5, R19/R20), not 3.

## End (PST)
- 14:42:05 ffmpeg SIGINT -> ~/recording/factory-run-8.mkv (53.3 MB). No room messages sent by me besides the dispatch.
- Room export ~/band-seats/room8-messages.jsonl (14 pages, 1,329 msgs) -> band-run-8/room-messages.jsonl; monitor log -> band-run-8/room8-log.jsonl; text digest band-run-8/texts.md. Logger + docker-events logger stopped.
- Message mix: 64 text, 515 tool_call, 502 tool_result, 188 task, 56 thought, 4 participant. Text chars: coordinator 39.4k (~33k spec paste), implementer 11.4k, reviewer 11.1k, spec tester 7.2k, human 2.7k.
- Containers at stop (implementer dossier-r8-impl-live-0778, spec tester dos-s1-spec-88318b38f492-*) -> logs in checks/hark-final-container-logs/, removed; network dos-s1-spec-88318b38f492 removed; final dossier-live8 removed after the live build. No containers, only bridge/host/none.
- Copied into checks/: handoff (handoffs/dossier-stage-1-handoff-run8.md), spec tester tree (spec-tester-run8/), implementer /tmp evidence (implementer-tmp/, live jsonl per candidate; SDK copy excluded), reviewer tree (reviewer-s1-run8-RIt0SqNT/, reports + isolated reports + live captures), Hark post-run outputs (hark-post/). band-run-8/result = result repo (HEAD 0778d05, 8 commits, clean); band-run-8/checks = full checks dir (31 MB).
- Isolated harness on final HEAD 0778d05 (stage 1 — highest reached; NOT accepted): state completed, mode isolated, claimed 1, 122/122 (test_auth 51, test_dossiers 60, test_sample 11), fabrications 0; stage-2 probe fail as expected. checks/run8-final-s1/, band-run-8/harness8.out.
- `harness check`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json) — expected (check8.out).
- Live runway.com (live8.sh: stage-1 @0778d05, bridge network, NIMBLE_BASE_URL=http://172.17.0.1:18443 exactly as given, no alias): 22:44:56–22:46:06 UTC (14:44:56–14:46:06 PST, 70 s), ready, spent_units 32 (forwarder 32). NOTE: research runs were blocked (402 trialNoQuota) for this build, so it used search + extract only. Saved band-run-8/dossier-runway.com.json.
  - legal_name "Runway Ai, Inc." (bizprofile.net table row "Foreign Legal Name") — CORRECT ignoring case (strict string differs: "Ai" vs "AI")
  - hq_city "New York" (PitchBook "Runway AI is headquartered in New York, NY.") — CORRECT (same city; strict string "New York City" differs)
  - ceo "Chang She" (runway.com/news/introducing-runway-fund: quote from LanceDB's CEO, a Runway Fund portfolio company) — WRONG. The page is on the subject's own site, so the new "own site = about the subject" rule let a third-party CEO through.
  - founded_year 2018 (corpdigest) — CORRECT
  - headcount_range "201-500" (PitchBook "Runway AI has 250 total employees.") — CORRECT (first run ever to get it)
  - funding_total 863,520,000 (Forge Global "Runway has raised $863.52M to date.") vs ~$859.5M: +0.47% — within 5%, not exact
  - Score 5/6 with funding ±5% and case/"City" normalisation; 4/6 with exact funding; strictly string-exact 2/6 (founded, headcount). Run 7: 4/6 ±5% (3/6 strict), run 6: 1/6, run 5: 4/6.

## Shared live set and how the gate behaved
- Set (reviewer, 14:09:38): apple.com (Apple Corps collision), etsy.com, dropbox.com; expected values from SEC filings and company pages; funding deliberately left without a reference value.
- Per-candidate correct counts (of 18):
  | Candidate | Implementer pass | Reviewer pass |
  |---|---|---|
  | 2aba421 (pre-candidate, unreported) | not reported (~228 units by window) | – |
  | f7c7fd4 (cand 1) | 8/18, 207 u, 202 s (Apple 2, Etsy 3, Dropbox 3) | 10/18, 185 u (Apple 3, Etsy 4, Dropbox 3) |
  | 69b589c (cand 2) | 8/18, 157 u (Apple 2, Etsy 3, Dropbox 3) | 9/18, 193 u (Apple 3, Etsy 3, Dropbox 3) |
  | 0778d05 (cand 3, unreviewed) | partial when stopped: Apple 4/6 (legal, HQ, 1976, 10001+; CEO Tim Cook stale), Etsy 4/6 (HQ, CEO, 2005, 1001-5000; legal unknown), Dropbox not finished; research runs 402 (Hark's grading of the jsonl vs the ledger values, citations not checked) | – |
- Behaviour: the shared set worked as intended for comparability (both seats on the same 3 subjects; no new-domain blocking disputes as in run 7) and the implementer did one pass per candidate (plus one unreported pre-candidate pass). But the same commit scored 8 vs 10 on the two seats' runs, and the reviewer blocked candidate 2 on a 10 -> 9 drop it said was provider-evidence variance, not code. Live noise (±1–2 per run) is larger than the gate's resolution, so the "any drop is blocking" rule produced a non-code blocker; the coordinator then set a target of recovering 10/18, which invites live tuning again (0778d05 "prioritize direct whole-company evidence").
- Live quality did improve on fields the new gathering rules target: headcount now correct on Apple/Etsy (0778d05) and on runway.com; funding total within 0.5% on runway; but the own-site rule admitted a portfolio company's CEO quote from runway.com/news.

## Nimble accounting (forwarder log band-run-8/nimble_fwd8.log; units8.py)
All seat live containers used host networking, so every call is attributed "host?uid0"; split by live-container windows (docker-events8.log) and the seats' own reports. Same unit model as run 7 (failed extracts 0).
| Seat / window | units |
|---|---|
| Stray run-7 seats (room 7, 14:06–14:13 + r3-live overlap ~14:17:33–14:19:50) | ≈ 92 + ≈ 55 = ≈ 147 |
| Reviewer preflight | ~1 (inside the stray window) |
| Implementer pre-candidate pass on 2aba421 (unreported) | 228 |
| Implementer f7c7fd4 pass | 207 (self-report; window 262 incl. stray overlap) |
| Reviewer review 1 | 180 (self-report 185) |
| Implementer 69b589c pass | 150 (self-report 157) |
| Reviewer review 2 | 187 (self-report 193) |
| Implementer 0778d05 pass (partial; 3 research 402s) | 124 |
| Spec tester / coordinator | 0 (mock/replay only) |
| Hark final runway | 32 |
| TOTAL through forwarder | 1,255 (run-8 seats ≈ 1,076; stray ≈ 147; final 32) — under the 2,500 limit, but the account's research quota ran out (402 trialNoQuota) at ~1,190 |
Implementer ≈ 709, reviewer ≈ 368. No 407s in tunnel.log this run (fresh tunnel at 14:04).

## Stage time table (min, from dispatch)
| | kickoff | live set fixed | TESTS w1 | CAND 1 | VERDICT 1 | TESTS UPD | CAND 2 | VERDICT 2 | CAND 3 | end |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 run 8 | 1.6 | 3.4 | 7.4 | 16.0 | REJECT 22.6 (review 6.3) | 24.4 | 27.9 | REJECT 32.7 (review 5.0) | 0778d05 ready ~34.2, not submitted | stopped 35.8 (Nimble 402 quota) |
| S1 run 7 | 1.4 | – | 9.0 | 26.2 | REJECT 33.3 (review 6.6) | 35.3 | 43.1 | stopped 45.0 | – | 45-min rule |
| S1 run 6 | 1.4 | – | 7.2 | 12.0 | REJECT 22.6 (review 10.4) | 24.1 | 26.2 | ACCEPT 32.5 | – | S1–S4 all accepted, 112.9 |

## Bottlenecks
1. External: the Nimble account's research quota ran out (402 trialNoQuota) 34 min in — hard stop before candidate 3 could be reviewed. ~147 units of the spend came from stray run-7 seats.
2. Live gate noise: same commit scored 8/18 (implementer) vs 10/18 (reviewer); a 1-field drop with no code cause became a blocker, and the follow-up target ("recover 10/18") pulled the implementer back toward live tuning.
3. Spec edge classes still surface only in review: wave 1 (23) and wave 2 caught the picosecond clock before the candidate, but leap seconds, multi-sentence and labelled research sentences, and invalid-import values came from reviewer probes (two rounds each for R5 and R19/R20).
4. Implementer still held candidate 2 ~3 min for its live pass despite two coordinator prompts, and ran one unreported live pass before candidate 1 (228 units).
5. Infra: interrupted run-7 turns resumed after the seat restart (stray seats); host-network live containers defeat per-seat attribution.

## Next generic tweaks (proposal, not applied)
- Reviewer/coordinator: the shared-set gate needs a noise margin. Run the shared set at most once per seat per candidate; block only when a field that was correct on the previous candidate becomes wrong or unknown on both seats' runs, or when the drop reproduces on a rerun / replay of the captured responses; otherwise carry it. Never set a live score target as a blocker.
- Reviewer: before blocking on a live drop, replay the previous run's captured provider responses through the new commit (the spec tester already builds these replay bundles); a drop that disappears on replay is provider variance and carries.
- Implementer: the live pass is reported on the exact candidate only and never delays the candidate — send the candidate when wave 1 passes and append live results as a follow-up (coordinator already asks for this; make it explicit in the implementer mandate). No live passes on intermediate commits.
- Implementer gathering rule refinement: a page on the subject's own site counts as about the subject only for statements about the subject itself; quoted statements by or about other organisations on that page (press releases, partner/portfolio quotes) are not evidence for the subject's people or numbers.
- Spec tester: wave 1 add one "spec time-format edge" test per timestamp input (leap second, offset crossing, sub-µs) and one "labelled sentence" test per extracted field — the classes that took two review rounds here.
- Operator (Hark, not mandates): before restarting seats, `band runtime interrupt` + `band detach` every room whose turns were cut off; check `pgrep -c codex` == 4 after the first handoff; check Nimble quota headroom before dispatch.

## Submission note
Run 8 ran factory-v2 1c07674 (= band-run-8/*.md). No stage accepted (stopped on Nimble quota at 35.8 min). Best full run remains run 6 (e104885). Nothing pushed/merged/submitted.

## Left running / state
VM up; sandbox tunnel.py pid 8529 (started fresh 14:04, log band-run-8/tunnel.log, 0 x 407); VM forwarder nimble_fwd7.py pid 465923 up on 127.0.0.1/172.17.0.1:18443 (GET /v2/agents 200 at end); seats stopped (agents + records kept); room-7 host sessions detached; no containers, no extra networks. ~/band-work/result and checks left in place for run 8 (rotate to -run8 before run 9; also the implementer's /tmp/dossier-r8-stage1-fixes worktree, branch stage1-review-fixes @0778d05). Nimble research runs currently return 402 trialNoQuota — a run 9 needs quota restored first.
