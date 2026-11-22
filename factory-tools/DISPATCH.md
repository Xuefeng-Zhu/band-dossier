# Judged dispatch template

## Before sending

Create a fresh Band room and workspace. Use [the host runner setup](../FACTORY.md#reproduce-the-setup) to put `continuation_operations.py` in `<WORKSPACE>/factory-prep/` and initialize the empty result checkout at `<WORKSPACE>/band-work/dossier-full-currency`. The `--currency-run` flag requires that exact directory name. Verify the commit and isolated check commands on a disposable fixture before dispatch. In the message below, replace `<WORKSPACE>` with the new workspace’s absolute path.

## Message

@frankzhu94/coordinator, run the judged Dossier build through phases 1–4 with `frankzhu94/implementer` and `frankzhu94/reviewer`.

Use the empty result checkout at `<WORKSPACE>/band-work/dossier-full-currency` for every phase. Each phase lives in `stage-N/` and holds a complete standalone service, a `Dockerfile` and a `RUN.md`. Leave the organizer checkout and its tests untouched.

Open the requirement files in order, one per phase.

- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-1.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-2.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-3.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-4.md`

Include the evidence requirement in both Stage 1 handoffs. Starting in Stage 1, keep a private evidence record for each build in its opaque state. Preserve the original text of every gathered page version, including evidence left out of the public response, along with the source URL, provider, available source metadata, and the provenance of provider-served claims. Associate each observation with its build and preserve the build’s timing, outcome, and spend. Carry this record through export and import. Review a same-stage round trip in scratch space, including builds that have identical public results and different underlying evidence. Verify that import preserves the original evidence without contacting providers. Keep credentials out of the audit record.

Run the host runner commands from the result root. Replace `N` with the current phase number.

```text
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run commit N "message"
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run check N <full-commit>
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run status <operation-id>
```

Builds and checks use the organizer mock web. Keep credentials out of the repository, commands, reports and messages.

This is the only human message. Follow your mandates and post the final report when you're done.
