# Band run 4 (Dossier, 4 seats) — notes

Started 2026-11-23 01:49 PST. Mandates work/band-dossier factory-v2 31f0b9d (local only, on top of dcd02a4; not pushed). Exact mandate copies: work/band-run-4/{coordinator,implementer,reviewer,spec-tester}.md (sha256 identical on VM ~/band-seats/mandates4/). Vocab scan (work/band-run-4/vocabscan.py, case-insensitive substring vs challenges/dossier/vocabulary.json): 0 hits in 4 mandates + dispatch.

## Mandate changes in 31f0b9d (generic)
- Coordinator: paste full requirement text at most once per seat per phase; later rounds path + commit + delta. Reviewer's VERDICT goes to implementer, spec tester and coordinator at once; coordinator records it, forwards to spec tester only if left out, doesn't re-relay findings.
- Implementer: start fixing on a reviewer's blocking finding with evidence (in a separate working copy so the reviewed commit stays checked out); gate next candidate on spec tester's TESTS UPDATED.
- Reviewer: start live runs in background on first candidate, in parallel, fold into first verdict; rerun live only if change can affect live output. VERDICT in one message to all three; blocking findings sent to implementer as soon as found.
- Spec tester: per requirement cover protocol edges (unsupported methods / unknown paths -> structured error), full precision of numbers/times, one injected transport fault per outside call, replay of captured real responses. On every REJECT add regression tests per blocking finding and send TESTS UPDATED.
- Dispatch (work/band-run-4/dispatch.txt): run-3 dispatch with the line "Every handoff carries the complete task and spec text, pasted." replaced by "Handoffs carry the task path, the spec path and the ledger; the full text is pasted once per seat per stage." Rest identical.

## Setup (PST)
- Instructions set for all 4 seats from ~/band-seats/mandates4/; `show --reveal --json` == file for all 4 (3415/4203/3668/1992 chars).
- Detached host session default-c80c81bf-… (run 3 room) from all 4 seats.
- Restart: plain `band restart` fails for coordinator/implementer/reviewer ("multiple hosted sessions"); `--host-session default` fails ("parked"). Worked: `band restart --host-session default-caa7ba06-…` (run-2 session, detached) — runtimes Connected, inboxes empty, run-2 room unchanged (last msg 00:58). Spec tester: plain restart OK.
- Result repo: ~/band-work/result -> result-run3 (HEAD 7e8e2cd), checks -> checks-run3; new empty result (git init -b main, Factory identity) and checks. No containers, no df- networks.
- Room b321b008-4bd1-4ab2-bbad-20955d33ed07 "Factory run 4": `band chat new --as coordinator --with implementer --with reviewer --with spec-tester`; human added `band chat add --as coordinator <room> 95a3f256-…`; `band room rename`. 5 participants. Each seat got a bound session default-b321b008-….
- Desktop switched to Factory run 4 (xdotool click 313,116), xscreensaver killed, xset s off -dpms.
- ffmpeg x11grab 2 fps -> ~/recording/factory-run-4.mkv (pid 232093, 01:53:4x).
- Monitor: ~/band-seats/logger4.py (pid 232131) -> ~/band-seats/room4-log.jsonl; v4.py tail; exp4.py export.
- Relay: sandbox tunnel.py pid 2244 up; VM 18443 GET /v2/agents -> 200.
- DISPATCH 01:53:56 PST, `band room send … --mention <coordinator id>`, text = run4/dispatch.txt. No other human messages.
- Stage 1 35-min deadline: 02:28:56 PST.

## Timeline (PST)
- 01:54:05 dispatch seen in room. 01:55:21–01:55:36 coordinator kickoff: spec pasted once per seat = 24 parts (8 × implementer/spec tester/reviewer), 100,017 chars, handoff file ~/band-work/dossier-stage-1-handoff.md; status to human 01:55:36.
- 01:55:51 implementer asks spec tester for suite command. 01:56:22 spec tester ambiguity (evidence strategy, unsupported-method code) -> 01:56:37 coordinator ruling.
- 02:00 / 02:05 / 02:08 implementer commits 3f548e4, b68bebd, f97011b, 717a0c3.
- 02:01:55 reviewer probes ready (probe list to implementer 406 chars, status to coordinator 345 chars), turn ended.
- 02:08:29 TESTS READY (to implementer only); 02:10:46 TESTS READY to coordinator + implementer (14.6 / 16.8 min after dispatch; run 3: 10.2).
- 02:13:02 CANDIDATE 1 717a0c3 (2,335 chars; spec suite 18/18 with live-patience 209.7 s, 17/17 Tavily variant; 12-company concurrent mock run 69/72 fields). 19.1 min after dispatch (run 3: 11.0).
- 02:13:17 coordinator review request: 1,020 chars, paths only, no spec re-paste (run 3: card + 8 parts ≈36k). Asked for VERDICT to all three seats.
- ~02:14 reviewer starts live container in background alongside isolated harness (new mandate working).
- 02:15:49 reviewer -> implementer blocking R15 (Unicode header treated as prose -> founded_year 1812). 02:16:50 implementer fix baebaa6 with regressions (1 min after finding, before verdict).
- 02:16:50 reviewer -> implementer live Cloudflare finding; 02:19:37 live Mercury finding.
- 02:20:07 VERDICT 1 717a0c3 REJECT (2,668 chars) to coordinator + implementer + spec tester in one message. 26.2 min after dispatch; review 6.8 min. Isolated harness 122/122 claimed 1 (82.9 s), stage-2 0/12 (expected). Blocking: R15 Unicode header; R15 live Cloudflare (founded 2020 from CA registry vs 2009 in gathered evidence; headcount 1001-5000 from a launch passage; 80 units, 142 s, 22 unanswered extracts, 25 research units unused); R15 live Mercury (namesakes: American Fidelity HQ, Mercury Systems CEO, Mercury General year; 96% satisfaction stat as headcount; 78 units, 275 s). Live spend 158 units.
- 02:20:37 spec tester asks which checks are blocking under the literal Appendix A; 02:20:37 / 02:20:53 coordinator ruling to reviewer and spec tester: only the Unicode header is blocking; entity/clause/percentage preferences diagnostic when citations satisfy Appendix A. Ruling NOT sent to the implementer.
- 02:21:08 reviewer shares sanitized live evidence file with implementer (on request).
- 02:22:08 TESTS UPDATED (2.0 min after verdict): unicode_headers, registry_and_launch, namesake_and_percentage cases.
- 02:19 / 02:23 / 02:26 / 02:28:32 implementer commits 5ce5227, 713d4fa, a789811, 5b36475 chasing live-quality items; no CANDIDATE posted.
- 02:28:56 Stage 1 hit 35 min without ACCEPT -> STOP. 02:29:03 `band stop` all 4 (agent + record kept), ffmpeg SIGINT -> ~/recording/factory-run-4.mkv (19.7 MB). No room messages sent.

## Post-stop artifacts (PST)
- Isolated harness on HEAD 5b36475 (clean tree): state completed, mode isolated, claimed stage 1, 122/122 stage 1, stage 2 fail (expected). VM ~/band-work/checks/run4-final-s1/report.json (copy in band-run-4/checks/run4-final-s1/).
- `harness check --track dossier`: 5 problems, all packaging (README.md, FACTORY.md, dossier-runway.com.json, mandates/, room.json missing) — expected for an unpackaged run repo.
- Live runway.com @5b36475 via relay (10:30:59–10:31:14 UTC, ~15 s): ready, 13 units. legal_name "Runway Growth Capital LLC" WRONG (namesake; correct Runway AI, Inc.); hq_city New York City CORRECT; ceo "Paige Thomas" WRONG (Rent the Runway; correct Cristóbal Valenzuela); founded_year 2018 CORRECT (clean citations this time); headcount_range 51-200 LIKELY STALE (LeadIQ "62 employees"; Feb 2026 ~140 per TechCrunch, late-2026 trackers 290–608); funding_total 859,500,000 CORRECT (aggregator consensus $859.5M). 3/6. File band-run-4/dossier-runway.com.json.
- Room export band-run-4/room-messages.jsonl (959 msgs: 48 text, 394 tool_call, 386 tool_result, 99 task, 28 thought). Text chars: coordinator 103k (100k = 24 spec-paste parts at kickoff), reviewer 6.0k, spec tester 5.8k, implementer 3.8k. Monitor log band-run-4/room4-log.jsonl (first-seen times).
- Result repo copy band-run-4/result (HEAD 5b36475). Handoff file + spec suite + reviewer ledger: band-run-4/checks/.
- Containers and df- networks removed; no codex/ffmpeg/logger processes. VM left running. Nothing pushed. Run 2/3 rooms untouched.
- Nimble units: reviewer live 158 (Cloudflare 80, Mercury 78) + final runway 13 = 171 metered; implementer (1 relay call) and spec tester (public-evidence capture, ~4 relay calls) not metered.

## Stage 1 time breakdown (min from dispatch 01:53:56)
kickoff 1.7 | reviewer probes 8.0 | TESTS READY 14.6 (both 16.8) | CANDIDATE 19.1 | review 6.8 (first blocking finding at +2.8 into review) -> REJECT 26.2 | blocking fix committed 22.9 (before verdict) | TESTS UPDATED 28.2 | stop 35.1, no 2nd candidate.
Run 3: CANDIDATE 11.0, REJECT 18.0, CANDIDATE 24.1, REJECT 33.7, stop 35.0. Run 2: CANDIDATE 14.6, REJECT 26.9, ACCEPT 56.5.

## Submission note
Final submission mandates must match what actually ran. Run 4 ran factory-v2 31f0b9d (= band-run-4/*.md); runs 3 = dcd02a4, 2 = b2f6bca. The repo's mandates/ folder must be set to the commit of the run that is submitted.
