# Judged dispatch template

## Before sending

Create a fresh Band room and workspace. Use the host runner setup to initialize the empty result checkout at `<WORKSPACE>/band-work/dossier-full-currency`. Copy `continuation_operations.py`, `review_check.py`, `browser_probe.py` and `currency_probe.py` from this directory to `<WORKSPACE>/factory-prep/`. The `--currency-run` flag requires the exact result directory name. [Host runner setup](../FACTORY.md#reproduce-the-setup)

Verify the commit and isolated check commands on a disposable fixture. Use a separate rehearsal room to verify that the actual Reviewer can invoke `currency` and `browser` on a clean fixture with the same permissions as in the judged run. Confirm the currency probe passes a known-correct commit and rejects a known regressed commit. In the message below, replace `<WORKSPACE>` with the new workspace’s absolute path.

## Message

@frankzhu94/coordinator, run the judged Dossier build through phases 1–4 with `frankzhu94/implementer` and `frankzhu94/reviewer`.

Use the empty result checkout at `<WORKSPACE>/band-work/dossier-full-currency` for every phase. Each phase lives in `stage-N/` and holds a complete standalone service, a `Dockerfile` and a `RUN.md`. Leave the organizer checkout and its tests untouched.

Open the requirement files in order, one per phase.

- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-1.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-2.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-3.md`
- `<WORKSPACE>/sf-buildathon-2026/challenges/dossier/spec/stage-4.md`

Include the evidence requirement in both Stage 1 handoffs. Starting in Stage 1, keep a private evidence record for each build in its opaque state. Preserve the original text of every gathered page version, including evidence left out of the public response, along with the source URL, provider, available source metadata, and the provenance of provider-served claims. Associate each observation with its build and preserve the build’s timing, outcome, and spend. Carry this record through export and import. Review a same-stage round trip in scratch space, including builds that have identical public results and different underlying evidence. Verify that import preserves the original evidence without contacting providers. Keep credentials out of the audit record.

Include the USD funding requirement from Appendix A.4 in both Stage 1 handoffs, and carry it forward as a required ledger item in every phase. Explicit foreign-currency amounts are ineligible even when they use a dollar sign. Interpret the qualifier in context, including currency labels before and after the amount. A foreign-currency amount in the same excerpt does not disqualify a separately supported USD amount. Preserve all valid USD forms. Apply the same support rule to page evidence and provider research claims used by the service. Build to the rule and let the isolated mock corpus supply its own cases.

Run the host runner commands from the result root. Replace `N` with the current phase number.

```text
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run commit N "message"
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run check N <full-commit>
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run currency N <full-commit>
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run browser N <full-commit>
/usr/bin/python3 -B <WORKSPACE>/factory-prep/continuation_operations.py --currency-run status <operation-id>
```

In every phase, give the Reviewer the currency command in the current handoff. After the organizer check, run it on the same candidate SHA. Acceptance requires a completed report for that SHA with all 13 currency cases passing. If any required case fails, send the finding back for correction in the current phase. Report the coverage of optional provider research separately.

From Stage 2 onward, include the browser command in the Reviewer’s current-phase handoff. After the organizer and currency checks, run it on the same candidate SHA to capture the six dossier routes at 375 px and 1440 px using Chromium on an internal Docker network. The report and screenshots support overflow, labels, visible keyboard focus and visual inspection. Review any additional browser behavior required by the current specification separately.

Builds and checks use the organizer mock web. Keep credentials out of the repository, commands, reports and messages.

This is the only human message. Follow your mandates and post the final report when you're done.
