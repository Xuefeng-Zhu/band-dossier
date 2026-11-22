@coordinator, run the judged build, phases 1–4. Seats: `frankzhu94/implementer`, `frankzhu94/reviewer`.

Track `dossier`. Result checkout, empty, used for every phase: `/home/frank/Documents/Codex/<NEW>/band-work/<NEW-RESULT>`. Each phase lives in `stage-N/` and holds a complete standalone service plus its `Dockerfile` and `RUN.md`. Leave the organizer checkout and its tests untouched.

Requirements, one per phase, opened in this order:
- `/home/frank/.../sf-buildathon-2026/challenges/dossier/spec/stage-1.md`
- `/home/frank/.../spec/stage-2.md`
- `/home/frank/.../spec/stage-3.md`
- `/home/frank/.../spec/stage-4.md`

Host runner, from the result root (N = phase):
```text
/usr/bin/python3 -B <ABS>/continuation_operations.py --currency-run commit N "message"
/usr/bin/python3 -B <ABS>/continuation_operations.py --currency-run check N <full-commit>
/usr/bin/python3 -B <ABS>/continuation_operations.py --currency-run status <operation-id>
```
Builds and checks use the organizer mock web. Keep credentials out of the repository, commands, reports and messages.

This is the only human message. Follow your mandates and post the final report when you're done.
