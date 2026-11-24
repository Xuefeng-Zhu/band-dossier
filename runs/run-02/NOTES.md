# Band run 2 (submitted Dossier run, rerun after run-1 stall) — notes

Started 2026-11-22 22:34 PST. Frank approved option B (mandate fix + fresh room + fresh result repo).

## Setup (PST)
- Mandates: work/band-dossier factory-v2 commit b2f6bca (not pushed): event-driven lines (never sleep/poll/wait inside a turn; reviewer ends turn once checks prepared; coordinator never asks a seat to wait). Uploaded to VM ~/band-seats/mandates/ and set via `band agent instructions set --as devstar3071/<seat> --instructions-stdin` (verified with `show --reveal`, identical text).
- Seat settings unchanged (verified `band runtime settings` / `policy`): coordinator gpt-6.2-sol medium, implementer gpt-6.2-astra high, reviewer gpt-6.2-sol high; approval never, danger-full-access, host_native.
- Old room sessions: `band detach --host-session default-991bd6e5-…` for all three. `band restart` re-activated the reviewer's old-room session for ~1 min (it had 16 queued old-room messages); interrupted + detached at 22:38. It posted nothing; the old room only gained two system lines "Reviewer was interrupted" (06:33 from the earlier `band stop`, 06:38 from my interrupt). Old room otherwise untouched.
- Leftover harness containers from run 1 (df-svc/df-web, started 22:32) removed.
- Result repo: ~/band-work/result moved to ~/band-work/result-run1 (b87af76), ~/band-work/checks -> ~/band-work/checks-run1. New ~/band-work/result: `git init -b main`, user Factory <factory@factory.example.test> (per-seat identities still come from spawn wrappers). New empty ~/band-work/checks.
- Nimble relay: sandbox tunnel.py (pid 18548) still up; VM forwarder 127.0.0.1:18443 GET /v2/agents -> 200.
- Runtimes: `band restart --as devstar3071/<seat>` 22:38 -> all Connected.
- Room: caa7ba06-a506-491d-bcab-50526ffd875e "Factory run 2" — created by coordinator (`band chat new --with implementer --with reviewer`), human added via `band chat add`, renamed via `band room rename`.
- Desktop: xscreensaver was running (screensaver over Desktop — run-1 recording likely has screensaver stretches); killed + `xset s off -dpms`. Desktop switched to Factory run 2.
- Recording: run-1 ffmpeg stopped (SIGINT) -> ~/recording/factory-run.mkv (189 MB) kept. New: ~/recording/factory-run-2.mkv (x11grab 2 fps, started 22:39:30).
- DISPATCH 22:39:38 PST (06:39:38 UTC) via `band room send … --mention coordinator`, text identical to band-run-1/dispatch.txt (vocab scan 0 hits). No further human messages.

## Timeline (PST)
- 22:39:38 dispatch -> 22:40 coordinator posts 8-part stage-1 handoff to implementer and reviewer (45-min box), status to human 22:40. Messages steered into active turns.
- 22:43 implementer commit acdd08f (partial); 22:49:46 reviewer CHECKS READY (s1-review probes) and ENDED its turn (fix works).
- 22:54:11 CANDIDATE 1 112482a (implementer); 22:54:32 coordinator 8-part exact-commit check request to reviewer.
- 22:58 / 23:01 reviewer posts findings to implementer (R18 double www normalisation on import, R5/R19 unsupported-method response, R14 research-only sentence, live-page finding); implementer queues fixes until review releases freeze.
- 23:05 reviewer more findings (R15 retry wire); 23:06:39 VERDICT 1 112482a REJECT (R18 import, HTML 501, research citation, R15 ...). Isolated harness s1-1: 122/122, claimed stage 1. 23:07:18 coordinator 8-part revision handoff to implementer.
- 23:17:38 CANDIDATE 1 (round 2) d8b4ce3; 23:18:03 coordinator 8-part revised exact-commit review to reviewer.
- 23:21–23:25 reviewer: d8b4ce3 fixes import/OPTIONS/Leadership; isolated s1-2 claimed; new R14 regression (inline link drops valid prose). 23:25:15 VERDICT 1 d8b4ce3 REJECT (round 2). 23:25:35 second revision handoff to implementer.
- 23:30:52 CANDIDATE 1 (round 3) 9067f4b; 23:31:13 third exact-commit review request.
- 23:36:07 VERDICT 1 9067f4b ACCEPT (round 3; isolated 122/122, 92 s). STAGE 1 wall: 22:39:38 -> 23:36:07 = 56.5 min (2 REJECT + 1 ACCEPT).
- NOTE 23:36: someone else committed c3e3d20 on work/band-dossier factory-v2 (adds spec-tester seat, changes mandates). The running seats use b2f6bca text; mandates in the final submission must match what ran.
- 23:37 stage 2 opened: coordinator froze stage-1, copied to stage-2, 5-part stage-2 handoff to implementer + reviewer.
- 23:38 brief change: at the end stop ffmpeg but do NOT stop the VM (run 3 with 4 seats follows; explains c3e3d20).
- 23:39 implementer commit 0af11c6 (stage-2 base from frozen stage-1 tree).
- 23:50:25 reviewer CHECKS READY 2 (R1–R36, ~/band-work/checks/s2-review) and ended turn; 23:50:37 coordinator status to human.
- 23:55 monitor takeover (new subagent): tunnel.py pid 18548 alive, VM forwarder 18443 -> 200. Implementer mid-turn (inbox 5 queued), stage-2 dev containers up.
- 00:04:20 CANDIDATE 2 36b4cb3 (implementer, round 1; stage-2 = 15 files); 00:04:5x coordinator review request to reviewer; reviewer turn 00:04:50, isolated harness s2-1 running.
- 00:09:45 reviewer posts R13/R22 defect to implementer (failed render -> static search text still cited); implementer confirms 00:11:11.
- 00:14:59 VERDICT 2 36b4cb3 REJECT (round 1): R13/R22 render-refusal (Quartz Harbor fixture: /rendered 500 but API published Miami/Lime Fox from search text). Isolated s2-1: claimed stage 2, 122/122 inherited + 12/12 stage-2, 67 s. Reviewer also ran live Apple (80 units, 197 s) and Shopify (79 units, 141 s) via relay — quality notes: historical leadership/HQ, unrelated funding, headcounts from unrelated counts.
- 00:15:24 coordinator 5-part stage-2 revision handoff to implementer; status to human 00:15:25.
- 00:20:52 CANDIDATE 2 (round 2) 8d09fd5 (publish only browser-verified candidates); 00:21:12 coordinator 5-part revised exact-commit review to reviewer.
- 00:26:24 VERDICT 2 8d09fd5 ACCEPT (round 2; isolated: claimed stage 2, 122/122 + 12/12). STAGE 2 wall: 23:36:07 -> 00:26:24 = 50.3 min (1 REJECT + 1 ACCEPT).
- 00:27:56 stage 3 opened: coordinator 6-part stage-3 handoff (45-min box), stage 2 frozen at 8d09fd5 tree a4ae133.
- 00:39:40 reviewer CHECKS READY 3 (R1–R49, checks/s3-review); 00:39:51 coordinator status to human. Implementer commits e0fbc05, d64ea0d, 1715fca (00:29–00:34).
- 00:48:04 CANDIDATE 3 4152a78 (implementer, round 1; stage-3 18 files, 221 MB image). Stage-3 implementation only ~20 min.
- ~00:56–01:00:17 RELAY OUTAGE: sandbox restarted (tunnel.py pid 18548 died, VM 18443 -> 502). Restarted tunnel.py (setsid, logs band-run-1/tunnel.log); stale VM sshd (pid 4169) held 127.0.0.1:18080 -> killed; tunnel up 01:00:17, 18443 -> 200. (Sandbox also lost paramiko; reinstalled.)
- 00:54:12 reviewer -> implementer R40/R41 (leap-second RFC 3339 cutoffs rejected); 00:57:05 R14/R24 coverage miss (arroyo-loom: registry URL never rendered, HQ sentence beyond 1,500-char search preview).
- 00:59:39 VERDICT 3 4152a78 REJECT (round 1): R14/R24 missed browser-visible source; R4/R40/R41 leap-second timestamps. Isolated: claimed stage 3, 143/143. 01:00:06 coordinator 6-part revision handoff.
- 01:05 Nov 23: Frank killed run 2 at stage 3 round 2 (S1 56.5m/2 rej, S2 50.3m/1 rej, S3 rejected once). Peers stopped, ffmpeg stopped.
