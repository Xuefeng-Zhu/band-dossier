### 14:06:21 Star Developer 3071 (2691)
@Coordinator You lead this factory run. Build all four stages of the track below, coordinating @devstar3071/implementer, @devstar3071/spec-tester and @devstar3071/reviewer, keeping every stage in its own complete, buildable folder.

Workspace root: /home/hark
Kickoff package (specs, harness): /home/hark/sf-buildathon-2026
Track: dossier
Result repository (absolute, shared by every seat): /home/hark/band-work/result
Check output directory: /home/hark/band-work/checks
Harness venv: /home/hark/sf-buildathon-2026/.venv (activate before running checks)

Stage order and specs (open each ONLY when its stage starts):
1. /home/hark/sf-buildathon-2026/challenges/dossier/spec/stage-1.md -> stage-1/
2. /home/hark/sf-buildathon-2026/challenges/dossier/spec/stage-2.md -> stage-2/ (copy of final stage-1/, then extend)
3. /home/hark/sf-buildathon-2026/challenges/dossier/spec/stage-3.md -> stage-3/ (copy of final stage-2/, then extend)
4. /home/hark/sf-buildathon-2026/challenges/dossier/spec/stage-4.md -> stage-4/ (copy of final stage-3/, then extend)

Rules for this run:
- Never open a later spec until the current stage folder is final and committed. Never change a folder after the next spec is opened.
- Each stage folder needs its own Dockerfile, RUN.md and complete source. No symlinks, no submodules, no nested .git.
- The mock web for local runs is described in /home/hark/sf-buildathon-2026/challenges/dossier/web/README.md.
- Check a stage from the kickoff root, one check at a time:
  python -m harness run --track dossier --repo /home/hark/band-work/result --stage N --out /home/hark/band-work/checks/sN-<k>
  The stage's final check uses --mode isolated. Want "claimed stage: N". The next stage's suite is expected to fail.
- The shipped checks are a small part of the judged suite. Build to the spec; never special-case test inputs or fixtures.
- Live web access for manual checks: credentials for the live web provider are already exported in every seat's shell environment (they point at a local forwarder; from inside a Docker container use http://172.17.0.1:18443). Never write them into the repository.
- The full text is pasted once per stage to the whole room; handoffs carry the task path, the spec path and the ledger.
- Do not ask me anything. Resolve choices inside the band and record rulings. If blocked, record the blocker and evidence as the stage outcome and continue if possible.
- Save wall-clock time: review and test-writing run in parallel with building.
- After stage 4 (or the last stage reached), post a final report: accepted revision per stage, claimed stage per folder, rejections and what they changed, and elapsed time.

### 14:07:52 Coordinator (302)
@Star Developer 3071 Stage 1 is open. The implementer, spec tester, and reviewer have the full requirements and are working in parallel. I’ll advance on an independently accepted exact commit with an isolated harness claim of stage 1, then freeze its folder before opening stage 2.

### 14:07:52 Coordinator (1273)
@Implementer @Spec tester @Reviewer Stage 1 spec 8/8 (last part)

An **amount** is written in one of these forms, matched without regard to case, with no
letter or digit directly before it or after it:

- `$`, `US$` or `USD`, an optional space, a number, and optionally a scale: `k`, `m`, `mn` or
  `bn` directly after the number, or one space and `thousand`, `million` or `billion`.
  Examples: `$12M`, `$12.5 million`, `US$12 million`, `USD 12 million`, `$12m`,
  `$12,000,000`.
- A number, optionally one space and `thousand`, `million` or `billion`, then one space and
  `dollars` or `US dollars`. Examples: `12 million dollars`, `12,000,000 US dollars`.

Amounts in other currencies are not amounts.

### A.5 Normalisation

| Field | Normalised value |
|---|---|
| `legal_name`, `hq_city`, `ceo` | The text as the excerpt writes it |
| `founded_year` | The number as an integer |
| `headcount_range` | The range of §4 that contains the number |
| `funding_total` | The number times the scale (`k` and `thousand` 1,000; `m`, `mn` and `million` 1,000,000; `bn` and `billion` 1,000,000,000) in US dollars. An amount that does not come to a whole number of dollars is not a value |


### 14:07:52 Coordinator (4528)
@Implementer @Spec tester @Reviewer Stage 1 spec 7/8

this rule splits it into exactly one sentence.

### A.2 The rule

An excerpt supports the value V for the field F of a company exactly when all of these hold:

1. It is a single sentence (A.1).
2. It names the company: it contains the company's normalised domain, or the company's
   name. The company's name is the first label of its domain with each `-` read as a space:
   `acme-robotics.test` is named by `Acme Robotics`.
3. It contains a statement phrase for F (A.3).
4. It contains none of the negating phrases (A.3).
5. It contains at least one value in F's format (A.4), and every value in F's format that it
   contains normalises to V (A.5).

The company's name, its domain and every phrase are matched without regard to case and as
whole words: the characters directly before and after the match are not letters or digits.
Phrases with a space match one space.

For example, for `acme-robotics.test`:

| Excerpt | Supports |
|---|---|
| `Dana Ruiz has led Acme Robotics as chief executive since 2021.` | `ceo` `Dana Ruiz` |
| `Acme Robotics CEO: Sam Ortiz.` | `ceo` `Sam Ortiz` |
| `Acme Robotics was founded in 2014.` | `founded_year` `2014` |
| `Acme Robotics employs about 120 people.` | `headcount_range` `51-200` |
| `Acme Robotics is reportedly in talks to raise $40M.` | nothing: a negating phrase |
| `Acme Robotics opened a sales office in Porto.` | nothing: no statement phrase for `hq_city` |

### A.3 Phrases

| Field | Statement phrases |
|---|---|
| `legal_name` | `legal name`, `registered name`, `registered as`, `registered company`, `legal entity`, `name of record` |
| `hq_city` | `headquartered in`, `headquarters in`, `head office in`, `based in`, `registered office in`, `registered seat in` |
| `ceo` | `chief executive officer`, `chief executive`, `CEO` |
| `founded_year` | `founded`, `founding`, `established`, `incorporated` |
| `headcount_range` | `employs`, `employees`, `staff`, `people`, `headcount`, `workforce` |
| `funding_total` | `raised`, `funding`, `invested`, `investment` |

The negating phrases are: `in talks to`, `plans to`, `planning to`, `wants to`,
`expects to`, `hopes to`, `aims to`, `seeking`, `could`, `would`, `might`, `reportedly`,
`rumoured`, `former`, `formerly`, `will become`, `not`.

### A.4 Value formats

A **capitalised word** is an uppercase letter followed by one or more lowercase letters,
with no letter or digit directly before or after it. The letters may be of any alphabet:
`Zürich` and `Müller` are capitalised words. An **uppercase word** is two or more uppercase
letters, with no letter or digit directly before or after it: `AI`, `USA`.

A **number** is written in digits, optionally with a `,` before each group of three digits
and a decimal part after a `.`: `120`, `1,200`, `12.5`, `12,000,000`. Digits directly next to
a letter, or joined to other digits by `,` or `.` in any other way, are not a number.

| Field | Format |
|---|---|
| `legal_name` | The company's name or its domain (matched as in A.2), then zero or more capitalised or uppercase words each after one space, then an optional `,`, one space, and a legal-form suffix with no letter or digit directly after it. Where several such texts start at the same place, the shortest counts |
| `hq_city` | A place name directly after a statement phrase for `hq_city` and one space: the longest run of capitalised words joined by single spaces or by `-` that starts there, not part of a longer such run |
| `ceo` | A person's name: a run of two or three capitalised words joined by single spaces that is not part of a longer such run. Occurrences of the company's name and of the statement phrases for `ceo` are first taken out of the sentence and separate the words around them |
| `founded_year` | A number of exactly four digits, from 1800 to 2099, that is not part of an amount |
| `headcount_range` | A number with no decimal part, 1 or more, that is not part of an amount. Words before it, such as `about` or `roughly`, do not change it. A stated range such as `51-200 employees` holds two numbers |
| `funding_total` | An amount (below) |

The legal-form suffixes, matched exactly as written here: `Inc.`, `Corp.`, `LLC`, `LLP`,
`L.P.`, `Ltd`, `Limited`, `Pty Ltd`, `plc`, `PLC`, `GmbH`, `AG`, `KG`, `SE`, `AS`, `A/S`,
`ASA`, `AB`, `Oy`, `Oyj`, `B.V.`, `N.V.`, `S.A.`, `S.A.S.`, `S.L.`, `S.r.l.`, `S.p.A.`,
`s.r.o.`, `a.s.`, `K.K.`.



### 14:07:52 Coordinator (4593)
@Implementer @Spec tester @Reviewer Stage 1 spec 6/8

| Search through `nimble`, depth `fast` (a truncated page body) | 5 |
| Search through `nimble`, depth `deep` (the full page) | 15 |
| Search through `tavily`, depth `lite` (title, URL and snippet) | 8 |
| Search through `tavily`, depth `fast` (title, URL and a longer snippet) | 16 |
| Search through `tavily`, depth `deep` (the full page) | 16 |
| Extract through `nimble` | 1 per URL requested, including a URL for which no page is returned |
| Extract through `tavily` | 2 per URL requested, including a URL for which no page is returned |
| Research run through `nimble` | 25 when the run is started; checking on or collecting a run costs nothing |

A search's depth is WebRouter's `search_depth`.

A search returns at most 10 results, whatever number it asks for. A call that a provider
refuses with an error status costs nothing. A call whose answer does not arrive, because it
times out or its connection fails, costs its units as in the table, whether or not the
provider received it. An extract that the provider answers with no page
for the URL is not refused: it costs its units, as in the table, whatever status says so. An
extract through `nimble` does not set `render`.

A build stops making provider calls before its spending would exceed 80 units, and completes
with the pages and research claims it has obtained.

A research request names the company by its domain in its query, and names the fields it
asks for by the field names in §4, as the property names of its output schema.

## 10. Export and import

The service must support `GET /_test/export` and `POST /_test/import`. Like reset, these
are unauthenticated control endpoints.
Exports may contain credentials and session tokens; handle them as private artifacts.
Return 200 from export with a JSON object containing `track: "dossier"`,
`format_version: 1` and `state` (an implementation-defined JSON object). The state format
is opaque to the caller and must be accepted unchanged by import.

Import takes that entire object and atomically replaces the service's state, returning
204. It must accept an unchanged export produced by this service. No dependency on the
source process, files, volume, port or network address is allowed. Import is replacement,
not merge; repeating it restores the exported state without duplicating anything. Invalid
JSON follows §5; missing fields, wrong track/version or an invalid state give 422
`validation_failed` without changing the destination. These control calls have a 10-second
timeout. Export is an atomic, read-only snapshot; subsequent source writes do not change it.

Preserve accounts and hashed-password login, existing bearer tokens, dossiers with their
ids, states, fields, citations, `researched_at` and `spent_units`, all completed idempotent
request bodies and original responses. Identities and timestamps must not be regenerated.
Import makes no provider call: imported dossiers are not researched again, and their
citations remain citations served to this service. Failed request keys remain reusable.
Existing tokens and retries must remain valid after import; replacing the state with a fresh
fixture does not satisfy this requirement. Import removes all previous destination data and
credentials. Reset clears all state, including imported state. Export and import do not
change the clock. State need not survive an abrupt container restart.

An export taken while a build is running holds the dossier as it was before that build;
after import, that dossier is in the state of its last completed build, or `failed` with
every field `unknown` when no build had completed.

## 11. Concurrency

Concurrent requests must produce the same results as executing them one at a time in some
order. The requirements above hold at every read.

## Appendix A. When an excerpt supports a value

This appendix is the whole definition of "supports" used in §4. The service decides support
by these rules alone.

### A.1 Sentences

A page's prose is split into lines at each line break, and each line into sentences. A
sentence ends after a `.`, `!` or `?`, together with any `"`, `”`, `’` or `)` directly after
it, when whitespace follows. A `.` that ends one of the legal-form suffixes in A.4, written
as a whole word, does not end a sentence. Each sentence is taken without its surrounding
whitespace; empty sentences are dropped.

An excerpt is a **single sentence** when, with every run of whitespace written as one space,


### 14:07:52 Coordinator (4551)
@Implementer @Spec tester @Reviewer Stage 1 spec 5/8

- A build whose provider calls each answer within one second ends within 10 seconds of the
  request that started it.
- That bound is not a deadline for slower providers. Against the live providers
  (`NIMBLE_BASE_URL` unset, or its host `sdk.nimbleway.com`), where a Nimble search can take
  over ten seconds and a research run about a minute, a build does not give up on a call
  that has been waiting less than 30 seconds, nor stop gathering because of the time it has
  run in its first 120 seconds. It still ends `ready` or `failed` within 300 seconds.
- Reading a dossier, listing dossiers and every other request except `POST /dossiers` and
  `POST /dossiers/{domain}/refresh` make no provider call.

### `POST /dossiers`

**An idempotent write path.** `Idempotency-Key` is required; see §7.

```http
POST /dossiers
Authorization: Bearer <token>
Idempotency-Key: 2f9c1a...

{ "domain": "acme-robotics.test" }
```

```json
202
{ "dossier_id": "d_7", "domain": "acme-robotics.test", "state": "building" }
```

When no dossier exists for the domain, the service creates one, starts its first build and
returns 202. When a dossier already exists for the domain, the service starts no build and
returns **200** with that dossier's `dossier_id`, `domain` and current `state`.

Concurrent requests for the same domain create one dossier and start one build, whatever
their keys.

| Case | Response |
|---|---|
| `domain` missing | 422 `validation_failed` |
| `domain` invalid after normalisation (§4) | 422 `validation_failed` |

### `GET /dossiers/{domain}`

```json
{
  "dossier_id": "d_7",
  "domain": "acme-robotics.test",
  "state": "ready",
  "researched_at": "2026-03-01T09:00:00+00:00",
  "spent_units": 34,
  "fields": {
    "legal_name": { "value": "Acme Robotics, Inc.", "status": "known", "citations": [ { "...": "..." } ] },
    "hq_city": { "value": "Lisbon", "status": "known", "citations": [ { "...": "..." } ] },
    "ceo": { "value": null, "status": "unknown", "citations": [] },
    "founded_year": { "value": 2014, "status": "known", "citations": [ { "...": "..." } ] },
    "headcount_range": { "value": "51-200", "status": "known", "citations": [ { "...": "..." } ] },
    "funding_total": { "value": 12000000, "status": "known", "citations": [ { "...": "..." } ] }
  }
}
```

- `state` is `building` while a build runs, otherwise the outcome of the latest build,
  `ready` or `failed`.
- `fields` always holds all six fields. Before the first build completes `ready`, every
  field is `unknown`. While a later build runs, `fields` are those of the last build that
  completed `ready`.
- `researched_at` is the time of the last build that completed `ready`, or null.
- `spent_units` is the total cost (§9) of every provider call made for this dossier, by
  every build, since it was created.
- The domain in the path is normalised (§4). No dossier for it is 404 `not_found`.

### `POST /dossiers/{domain}/refresh`

**An idempotent write path.** `Idempotency-Key` is required; see §7. No body.

Starts a new build of the dossier and returns 202 with
`{ "dossier_id", "domain", "state": "building" }`. A refresh received while a build of the
dossier is running starts no second build and returns 202 with the same body.

A refresh researches again: its build makes provider calls whether or not anything has
changed since the last build, and its spending counts in `spent_units`.

| Case | Response |
|---|---|
| No dossier for the domain | 404 `not_found` |

### `GET /dossiers`

```http
GET /dossiers?q=acme&limit=50&offset=0
```

```json
{ "dossiers": [ { "dossier_id": "d_7", "domain": "acme-robotics.test", "state": "ready",
                  "legal_name": "Acme Robotics, Inc.", "researched_at": "2026-03-01T09:00:00+00:00",
                  "spent_units": 34 } ],
  "has_more": false }
```

- `legal_name` is the value of the dossier's `legal_name` field, or null.
- `q` is optional. When present, only dossiers whose domain or `legal_name` contains `q`,
  compared case-insensitively, are listed. An empty `q` lists every dossier.
- Dossiers are ordered by domain ascending.
- `limit` defaults to 50, range 1 to 200. `offset` defaults to 0. `has_more` is true when
  items exist beyond the last one returned.

## 9. Providers and cost

Each provider call has a cost in **units**:

| Call | Cost |
|---|---|
| Search through `nimble`, depth `lite` (title, URL and snippet) | 1 |


### 14:07:52 Coordinator (4529)
@Implementer @Spec tester @Reviewer Stage 1 spec 4/8

Requests must not produce 5xx responses, including under concurrent load and when a
provider endpoint answers with an error.

## 6. Authentication

Authentication supports signup and login. Email verification, password reset, refresh
tokens and role-management endpoints are out of scope.

```http
POST /auth/signup
{ "email": "a@example.com", "password": "correct horse", "display_name": "Ada" }

->  201  { "user_id": "u_1", "display_name": "Ada", "token": "..." }
```

```http
POST /auth/login
{ "email": "a@example.com", "password": "correct horse" }

->  200  { "user_id": "u_1", "display_name": "Ada", "token": "..." }
```

| Case | Response |
|---|---|
| Email already registered | 409 `email_taken` |
| Password shorter than 8 characters | 422 `validation_failed` |
| `email` not of the form `local@domain` | 422 `validation_failed` |
| `display_name` empty or longer than 100 characters | 422 `validation_failed` |
| Wrong password or unknown email on login | 401 `unauthenticated` |

For a user seeded by the fixture (§3.3), `user_id` is that user's `id` in the fixture.

Every other endpoint requires a bearer token, except `/health`, the `/_test/*` endpoints and
the two above. A request to such an endpoint that lacks a valid token is 401
`unauthenticated`, even when it also lacks a required `Idempotency-Key`.

```http
Authorization: Bearer <token>
```

Tokens do not expire. An account may have multiple valid tokens and concurrent sessions.

Passwords must be stored using a password-hashing function such as bcrypt, scrypt or
Argon2, or an equivalent. Plaintext password storage is not permitted.

## 7. Idempotency

Two write paths require an idempotency key (§8): **`POST /dossiers`** and
**`POST /dossiers/{domain}/refresh`**. Everything below applies to each of them
independently.

```http
Idempotency-Key: <client-chosen string, 1..255 characters>
```

The key is scoped to **the authenticated user**. Two different users may use the same key string
with no interaction between them.

A replay means the same user sending the **same method, the same path and the same body**. The
same key with the same body on a different path is a different request, not a replay, and must
succeed normally. `Acme-Robotics.test` and `acme-robotics.test` in a path or body are different
requests for this rule, though they name the same dossier.

| Situation | Response |
|---|---|
| Header absent or empty | 400 `missing_idempotency_key` |
| First use of the key | The normal response (§8) |
| Replay: same key, same body | **200**, body identical to the original response as a JSON value |
| Same key, different body | 409 `idempotency_key_reuse` |
| Key reused after the original request failed with 4xx | Treated as a first use |

"Same body" means the same JSON value after parsing — key order and whitespace do not matter.
Unknown fields are ignored (§3.5) and play no part in this comparison: a body that differs
from the first only in unknown fields is the same body, so the request is a replay.
`POST /dossiers/{domain}/refresh` takes no body; any body sent to it is ignored and plays no
part in deciding a replay.

For concurrent identical requests with an unused key, exactly one returns the normal
response. The others return 200 with the same body. The operation takes effect only once.

A successful replay returns the original response, even after the dossier has changed. It
starts no build and makes no provider call.

After the body has parsed as a JSON object and the caller is authenticated, an already
claimed key is resolved before field validation. Thus changing a successful request to an
invalid body with the same key still returns `409 idempotency_key_reuse`.

## 8. API

### Builds

A **build** researches one dossier: it calls the providers, decides each field, and replaces
the dossier's fields with the result when it completes. A dossier's first build starts with
`POST /dossiers`, and every later one with `POST /dossiers/{domain}/refresh`. A build's
**time** is the clock's time when the request that started it was received.

- A dossier has at most one build running at a time.
- A build ends in `ready` when it completed, or `failed` when none of its provider calls
  succeeded. A failed build leaves the fields as they were.
- When a build completes `ready`, each field is `known` exactly when the evidence (§4)
  supports a value for it.


### 14:07:52 Coordinator (4572)
@Implementer @Spec tester @Reviewer Stage 1 spec 3/8

claim that a `nimble` research run for the company asking for all six fields answers with.

Of the searches that a provider answers without an error, every build makes exactly one whose
query is exactly the company's normalised domain, through a provider of its choice; its other
such searches use other queries. A search that a provider answers with an error does not
count. The pages whose text a build obtains from providers are the pages it **gathers**.

A **citation** is an excerpt of text a provider served for the page at `url`:

- The excerpt is copied character for character from that served text, except that any run
  of whitespace may be written as a single space. It is 1 to 500 characters long.
- It is taken from the page's prose (below), not from its header.

An excerpt **supports** a value when, read on its own, it states that value for that field
of this company, as Appendix A defines. The excerpt may write the value differently from the
API: `Acme Robotics has raised $12M.` and `Acme Robotics has raised 12 million dollars.` both
support a `funding_total` of `12000000`, and `Acme Robotics employs about 120 people.`
supports a `headcount_range` of `51-200`.

A research answer carries a claimed value for a field and a citation for the claim. The
claim is asserted only when its citation supports it. A field is `unknown` when no evidence
supports a value for it, even when a research answer claims one.

When the evidence supports more than one value for a field, the field holds one of them and
cites only excerpts that support that value.

### Pages

Every page has a URL, a title and a text. A text may begin with **header lines**, each of
the form `Name: value`, where the name is a capitalised word or several joined by `-`. The
header ends at the first empty line; everything after it is the page's **prose**. A text
whose first line is not a header line has no header and is all prose.

The header line `Facts:` carries a JSON object on the same line. Its keys are field names
from the table above, and its values are what the page states for those fields, in any
format. It is informative only: citations come from the prose, and whether an excerpt
supports a value is decided by Appendix A alone. The service may ignore other header lines.

### Fixture format

```json
{
  "now": "2026-03-01T09:00:00+00:00",
  "users": [
    { "id": "u_ada", "email": "ada@example.com", "password": "correct horse",
      "display_name": "Ada" },
    { "id": "u_bob", "email": "bob@example.com", "password": "correct horse",
      "display_name": "Bob" }
  ]
}
```

- `now` is required and sets the clock (§3.4).
- Seeded users must be able to log in with the given password immediately.
- A fixture with two users sharing an email is a reset error: 422 `validation_failed`,
  changing nothing.

## 5. Errors

Every 4xx and 5xx response carries this body:

```json
{ "error": { "code": "not_found", "message": "human readable, any wording" } }
```

Use the specified HTTP status and `code`. The human-readable `message` may use any wording.
Endpoint-specific errors are listed with each endpoint.

| Status | `code` | When |
|---|---|---|
| 400 | `malformed_request` | Unparseable body, or a field of the wrong JSON type |
| 400 | `missing_idempotency_key` | Required `Idempotency-Key` header absent or empty |
| 401 | `unauthenticated` | Missing, malformed or unknown bearer token |
| 404 | `not_found` | No such resource, or not visible to this caller |
| 409 | `idempotency_key_reuse` | Key already used by this caller with a different request body |
| 422 | `validation_failed` | A required field or query parameter is missing, or a stated rule is violated with no more specific code |

A field of the correct JSON type with an invalid format or out-of-range value gives
422 `validation_failed`, unless an endpoint specifies a different error. In addition:

- An integer-valued **query parameter** is written as plain decimal digits: `1e9`, `4.0` and `+4`
  are 422 `validation_failed` whatever their numeric value.
- Reserve 400 `malformed_request` for a body that does not parse or a field of the wrong type.

Shared ranges, enforced on every endpoint that takes them:

| Field | Valid | Otherwise |
|---|---|---|
| `Idempotency-Key` | 1 to 255 characters | 422 `validation_failed` |
| `limit` | integer 1 to 200 | 422 `validation_failed` |
| `offset` | integer 0 or more | 422 `validation_failed` |



### 14:07:52 Coordinator (4556)
@Implementer @Spec tester @Reviewer Stage 1 spec 2/8

### 3.2 Health

```http
GET /health  ->  200  {"status": "ok"}
```

Return 200 once the service and its data store can serve requests, within 60 seconds
of container start. Non-200 responses are permitted before the service is ready.
`/health` makes no provider call.

### 3.3 Reset and seed

```http
POST /_test/reset
Content-Type: application/json

{ ...fixture... }

->  204 No Content
```

Replace all service state with the fixture in the request body (§4). When reset returns
204, subsequent requests must see only that fixture: no users other than the seeded ones,
no dossiers and no stored idempotent responses. Repeated resets are supported. A build
still running when reset is called must not change the state that follows the reset.
This control endpoint must be enabled in the delivered image and requires no authentication.

### 3.4 Clock

The service keeps a clock that only reset and `POST /_test/clock` move. Every timestamp
the service records or returns is read from this clock.

```http
POST /_test/clock
Content-Type: application/json

{ "now": "2026-03-01T09:30:00+00:00" }

->  204 No Content
```

- Reset sets the clock to the fixture's `now`. Before the first reset the clock follows the
  system time.
- The clock stands still between calls: two requests with no clock call between them read
  the same time.
- `now` is an RFC 3339 timestamp with an explicit offset. A `now` earlier than the clock's
  current time is 422 `validation_failed` and changes nothing.
- `POST /_test/clock` requires no authentication.

### 3.5 Conventions

- Requests and responses are `application/json; charset=utf-8`.
- Timestamps in responses are RFC 3339 with an explicit offset, e.g. `2026-09-24T19:00:00+02:00`.
- Unknown fields in a request body are ignored, never an error.
- Unknown query parameters are ignored.
- IDs are opaque strings of at most 64 characters. Their format is yours.

## 4. Model

### Users

Users sign up and log in (§6). Every authenticated user sees the same dossiers.

### Domains

A company is identified by its domain. Every domain the API takes, in a body or a path, is
first **normalised**: surrounding whitespace removed, lowercased, one trailing `.` removed,
and one leading `www.` removed. The normalised domain must then be a valid host name: two or
more labels separated by `.`, each label 1 to 63 characters of `a-z`, `0-9` and `-`, not
starting or ending with `-`, and 253 characters or fewer in total. Anything else, including a
URL with a scheme or a path, is 422 `validation_failed`.

`Acme-Robotics.TEST.`, `www.acme-robotics.test` and `acme-robotics.test` name the same
company and the same dossier. Responses always carry the normalised domain.

### Fields

A dossier has exactly these six fields:

| Field | Value |
|---|---|
| `legal_name` | String: the company's registered name, e.g. `Acme Robotics, Inc.` |
| `hq_city` | String: the city of the company's headquarters, without region or country, e.g. `Lisbon` |
| `ceo` | String: the full name of the company's chief executive, e.g. `Dana Ruiz` |
| `founded_year` | Integer: the year the company was founded, e.g. `2014` |
| `headcount_range` | String: one of `1-10`, `11-50`, `51-200`, `201-500`, `501-1000`, `1001-5000`, `5001-10000`, `10001+` |
| `funding_total` | Integer: total equity funding raised, in whole US dollars, e.g. `12000000` |

A string value is written as the supporting excerpt writes it, without surrounding
whitespace. A headcount the web states as a number, or as a range that fits inside one of
the ranges above, has the range that contains it as its value.

Each field in a response has this shape:

```json
{ "value": "Dana Ruiz", "status": "known",
  "citations": [ { "url": "https://acme-robotics.test/about",
                   "excerpt": "Dana Ruiz has led Acme Robotics as chief executive since 2021.",
                   "provider": "nimble" } ] }
```

- `status` is `known` when `value` is not null, and `unknown` when it is.
- A `known` field has one or more citations. An `unknown` field has `"value": null` and
  `"citations": []`.
- `url` is the URL of the page the excerpt was served for, `provider` is `nimble` or
  `tavily`, the provider that served it.

### Evidence and support

The **evidence** for a company is every page that some search, through any provider and for
any query naming the company (as in Appendix A.2), returns, with its full text, and every


### 14:07:52 Coordinator (5274)
@Implementer @Spec tester @Reviewer Stage 1 spec 1/8

Open stage 1 only. Shared local handoff and ledger R1–R25: /home/hark/band-work/dossier-stage-1-handoff-run8.md
Implementer, take board #1 and build the API in stage-1. Deliver CANDIDATE 1 <full commit> once wave 1 passes that commit.
Spec tester, take board #2 and write independent wave-1 acceptance tests now. Share an absolute path and command with the implementer and me.
Reviewer, take board #3, fix the three independently sourced live subjects in the handoff now and prepare independent checks. End your turn when ready. I’ll request review on the exact wave-1-passing commit.
The numbered parts below carry the full requirements as one set. No separate receipt needed per part.

# Dossier — Stage 1: company profiles

This stage defines the initial service and its API.

Build from the supplied requirements. Source code, API documentation and schemas from
existing products in this domain must not be used.
WebRouter's own documentation may be used.

## 1. Scope

A caller asks for a company by its web domain. The service researches the company on the web
and keeps a **dossier**: a profile of six fields, each with the value the web supports and the
excerpts it came from. A dossier is built in the background, read any number of times, and
refreshed on request. Only the HTTP API is required.

The following apply to all operations, including concurrent requests and retries:

1. Every value the service asserts cites at least one excerpt that a provider endpoint served
   to this service, and that excerpt supports the value. No citation is invented, reworded, or
   attached to a value it does not support.
2. No build of a dossier spends more than 80 units (§9).

Contact data, people search, and fields other than the six in §4 are out of scope.

## 2. Delivery and deployment

Deliver an HTTP service, a `Dockerfile` and a `RUN.md` with a command that builds and
starts the service without manual setup. Language, framework and storage are unrestricted.
A `docker-compose.yml` is optional.

The submission is a containerized HTTP service, not a Python package. Python is not
required in the implementation. TypeScript/JavaScript, Go, Rust, Java, Python and any
other language are equally valid. The submitted `Dockerfile` is built and started,
and only its HTTP behavior is exercised; it does not import or execute the
submission's source files on the host that runs it.

The image must run on its own with `-e PORT=<port>` and a port mapping. All runtime
dependencies, initialization and seed data must work within that single container. Compose
configuration is not used to start the service.

### Web access

Two providers are available: `nimble` and `tavily`. Nimble is the default provider: every
service must be able to research companies using Nimble alone. Tavily is optional: a service
may use it beside Nimble, and its absence must not prevent research while Nimble answers.
The live submission and optional live judging provide a working Nimble key only.

The service reaches the providers only through WebRouter, the Python package `webrouter`
(module `web_router`). The service may be written in any language, but every request to a
provider goes through `web_router`: called in-process, or from a Python helper process that
the service runs inside its own container. The stage folder's dependency manifest lists
`webrouter>=0.12.0`. Calling a provider's API by any other route is not permitted.
Install it and the provider SDK dependencies from PyPI, including in the service's Docker build:

```sh
pip install "webrouter[search,extract,research]>=0.12.0"
```


The deployment provides these environment variables:

| Variable | Meaning |
|---|---|
| `PORT` | The port to listen on (§3.1) |
| `NIMBLE_API_KEY` | Credential for the `nimble` provider |
| `NIMBLE_BASE_URL` | Base URL of the `nimble` provider endpoint |
| `TAVILY_API_KEY` | Credential for the `tavily` provider |
| `TAVILY_BASE_URL` | Base URL of the `tavily` provider endpoint |

Keys are opaque non-empty strings. WebRouter's `nimble` provider reads `NIMBLE_API_KEY` and
`NIMBLE_BASE_URL` from the environment, and its `tavily` provider reads `TAVILY_API_KEY`. A
service that uses Tavily passes its base URL to WebRouter in `provider_config`:

```python
provider_config={"tavily": {"api_base_url": <TAVILY_BASE_URL>}}
```

### Resource limits

The service must operate within these limits:

| Limit | Value |
|---|---|
| CPU | 2 vCPU |
| Memory | 3 GiB |
| Start to first healthy response | 60 s |
| Concurrent requests | up to 50 in flight |
| Per-request timeout | 5 s (10 s for `POST /_test/reset`) |
| Outbound network | available during `docker build`; at run time, **only the provider endpoints this specification lists** |
| Disk | ephemeral; state need not survive a container restart |

Runtime assets and dependencies must be included in the image. This includes fonts,
scripts and stylesheets; external services other than the provider endpoints this
specification lists are unavailable at runtime.

## 3. Runtime contract

### 3.1 Listening

Listen on `0.0.0.0` using the `PORT` environment variable, default `8080`.



### 14:09:38 Reviewer (410)
@Coordinator @Implementer @Spec tester The R25 live set is fixed in /home/hark/band-work/dossier-stage-1-handoff-run8.md: apple.com (collision with Apple Corps), etsy.com, and dropbox.com. The handoff has the source-checked values and comparators, including the September Apple CEO transition and Dropbox’s current co-CEOs.

### 14:10:39 Reviewer (450)
@Coordinator @Implementer The configured Nimble URL uses host loopback. The default Docker bridge could not reach it. A 2-vCPU, 3-GiB container using Docker host networking reached the exact configured URL through WebRouter and got one Nimble lite result in 6.54 s. Live candidate runs can use host networking with a private test port. The shipped checks will use the isolated Docker network.

### 14:13:41 Spec tester (687)
@Implementer @Coordinator TESTS READY 1 wave 1 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py
Run `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit FULL_COMMIT`. R1–R15 cover packaging, HTTP, auth, idempotency and lifecycle. R16–R20 cover Nimble-only research, calls and costs, refusal handling, six marked-up sole-source fields and unsupported-claim rejection. R21–R24 cover portable snapshots, races and exact-commit acceptance. R24–R25 independent review and live checks have a separate record verifier described in the README. Fixture structure and isolated mock transport are verified.

### 14:13:56 Spec tester (329)
@Coordinator Wave 1 is ready and shared with the implementer. Run `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit FULL_COMMIT`. I verified the fixture inventory and isolated mock transport. The full candidate run and independent live gates are pending candidate evidence.

### 14:14:27 Spec tester (400)
@Reviewer If your planned exact-candidate live run can capture Nimble search, extract or research response JSON, please share redacted response bodies and request path/depth metadata for offline wave-2 replay. Local shared scratch directory /home/hark/band-work/spec-tester-run8/stage1/replays is available. Exclude credentials and headers. No extra paid calls needed.

### 14:14:57 Reviewer (502)
@Coordinator Stage 1 review preparation is complete. The handoff fixes apple.com, etsy.com and dropbox.com, with independently checked references and Apple Corps as the name collision. The configured Nimble route returned one lite result in 6.54 seconds through WebRouter in a resource-limited Docker container using host networking. I validated the independent probe scripts and started their mock fixture successfully. Board #3 is in progress for the exact-commit review.

### 14:14:57 Reviewer (372)
@Implementer Independent Stage 1 probes are ready. I’ll check domain and request-validation boundaries, replay order and raw path scope, concurrent create and refresh, failed-refresh reads, worker fencing at reset and import, clock behavior across containers, sentence and citation support, and provider routing and spend against the call log.

### 14:15:58 Implementer (331)
@Coordinator The stage image runs. All 12 sample dossiers reached ready within 2.2 seconds under the CPU and memory limits. Their cumulative spend matched the provider log at 502 units, with no build above 53. A separate two-provider outage returned failed at zero units. The fixed live set is running.

### 14:16:43 Reviewer (445)
@Spec tester I’ll capture the buffered Nimble JSON responses from the live candidate run and put checked, redacted files in /home/hark/band-work/spec-tester-run8/stage1/replays under the full revision. I verified the capture in Docker with synthetic traffic. It preserves response content and method, path, depth and status metadata while removing credentials and excluding all HTTP headers and extra provider calls.

### 14:17:14 Spec tester (424)
@Coordinator R6 ambiguity in wave 2: GET /dossiers/vela-works.test/refresh can be read as an unsupported method on the refresh path or as a malformed domain caught by GET /dossiers/{domain}. I propose treating it as an unsupported method (structured 404 or 405), but will accept structured 422 for this overlapping route until you resolve the reading. Unknown paths still require structured 404.

### 14:17:29 Implementer (367)
@Spec tester @Coordinator The image for f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb is ready. The 12-domain sample recorded 69 known fields and matched the mock’s 502-unit total. Fifty concurrent same-key creates produced exactly one 202. Please send the wave‑1 command when ready so I can run it on this commit.

### 14:17:29 Coordinator (609)
@Implementer @Spec tester @Reviewer R6 ruling for an authenticated GET /dossiers/{domain}/refresh: Stage 1 specifies POST on that route and supplies no status/code for an unsupported GET. Require a structured 4xx error envelope and leave the choice among 404, 405 and 422 outside the acceptance gate for this overlap. Continue enforcing the specified domain validation on supported routes and structured 404s for authenticated requests to unknown paths. Recorded in /home/hark/band-work/dossier-stage-1-handoff-run8.md.

### 14:17:44 Coordinator (336)
@Implementer Wave 1 is ready. Run `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb`. Send the exact-commit receipt with `CANDIDATE 1 f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb` once it passes. R1–R24 apply, and R25 live evidence may follow.

### 14:17:59 Spec tester (814)
@Implementer @Coordinator TESTS READY 1 wave 2 /home/hark/band-work/spec-tester-run8/stage1/wave2.py
Run `python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit FULL_COMMIT`. Covers startup clock and protocol error envelopes, exact timestamp and funding precision, Unicode/prose edges, one truncated reply per used Nimble operation, and import fencing/portability after source removal. Verified the proxy emits a genuine partial-body socket close. Live-response replay is supported with `--replay`; no capture was available at dispatch. Preliminary run on f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb found R5: fixture time ...123456789123, then a one-picosecond-earlier timestamp is accepted with 204 instead of 422. Isolate with `--test R05`.

### 14:18:14 Coordinator (329)
@Reviewer Wave 2 from the spec tester is ready, with a reproducible R5 fractional-clock finding on f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. The command and finding are in /home/hark/band-work/dossier-stage-1-handoff-run8.md. Include this check once you receive the exact candidate review request.

### 14:18:30 Spec tester (326)
@Implementer Wave 1 is ready. Run `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb`. It archives and rebuilds the Stage 1 tree from that exact SHA, using the isolated mock and a fresh destination container for state portability.

### 14:18:30 Spec tester (218)
@Coordinator Wave 2 now enforces only the structured 4xx envelope for authenticated GET on the refresh overlap. The unknown-path tests still enforce 404 not_found. Fixture self-test passed.

### 14:20:46 Implementer (800)
@Coordinator R25 live baseline on f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb completed in 202.45s. Eight of 18 fields had correct values and supporting excerpts, at 207 units total (25.88 per correct field). Apple: legal name and HQ, 70 units/130.34s. Etsy: HQ, CEO and founding year, 69 units/202.45s. Dropbox: HQ, co-CEO and founding year, 68 units/99.38s. All emitted excerpts matched stored provider text. The two coincidentally correct headcount bins cited a year or a URL number, Etsy’s headcount cited an address, and its funding cited one round. Apple’s CEO and founding year were wrong. Dropbox’s $607M source reports aggregate funding without specifying equity. These receive no credit. Public-response-only measurements are in /tmp/dossier-r8-impl-live-f7.jsonl.

### 14:21:01 Implementer (580)
@Coordinator Stage 1 is implemented at f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb in the clean shared checkout. The image built from a Git archive. All 12 sample dossiers finished ready within 1.52s, all 69 citations matched served text, and the provider and API both counted 502 units. Concurrent creation and cross-container state transfer passed. The live baseline was 8 supported correct fields across 3 companies at 207 units. The independent wave‑1 command is the remaining candidate gate. I’ll run it on this commit when the spec tester sends it.

### 14:22:17 Implementer (1830)
@Coordinator CANDIDATE 1 f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. Wave 1 passed all 23 executed checks. Command: `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb`. Receipt: /tmp/dossier-r8-wave-f7.log. The shared checkout is clean.

R1 clean-archive Docker build and RUN.md. R2 health without provider traffic. R3 50 concurrent reads. R4 reset validation and stale-build fencing. R5 clock and timestamps. R6 typed input and structured errors. R7 account validation and multiple sessions. R8 bearer precedence. R9 normalized shared domains. R10 replay scope, precedence and original body. R11 concurrent creation. R12 coalesced refresh. R13 pending, ready and failed fields. R14 list filtering, ordering and pagination. R15 background timing and request-start clock. R16 Nimble-only research and provider-free reads. R17 exact-domain search and six-field research schema. R18 refusals, observed spend and no render. R19 six independent sole-source facts. R20 negation, ambiguity, header-only and unsupported claims. R21 in-flight export fallback. R22 portable import, replacement and unchanged clock. R23 concurrent keys and provider failures. R24 exact-commit wave 1 passed; independent verdict and final harness claim are pending.

R25 measured once on this commit with the supplied Nimble endpoint. Apple had 2 supported correct fields at 70 units in 130.34s, Etsy had 3 at 69 units in 202.45s, and Dropbox had 3 at 68 units in 99.38s. Total 8/18 at 207 units, or 25.88 units per supported correct field. This establishes the first-candidate baseline. Headcount, single-round funding, Apple CEO and incorporation/founding confusion account for missed credit. Public result and citation detail: /tmp/dossier-r8-impl-live-f7.jsonl.

### 14:22:32 Coordinator (630)
@Reviewer REVIEW 1 f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. Handoff: /home/hark/band-work/dossier-stage-1-handoff-run8.md. Clean HEAD and exact-commit wave 1 verified, 23/23, receipt /tmp/dossier-r8-wave-f7.log. Review R1–R25 from this commit, including the R5 wave 2 reproduction, current live baseline and Appendix A evidence, and the serialized isolated stage 1 harness check. Include the claim, check counts, live correct outputs and provider spend, elapsed time and supported verdict evidence. Send VERDICT 1 f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb ACCEPT|REJECT to all three seats together.

### 14:23:33 Reviewer (612)
@Implementer Blocking R5/R13 on f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. Exact-commit Wave 2 reproduced HTTP 204 when the clock was moved one picosecond backward; the expected result is 422 validation_failed with unchanged time. server.py timestamp() passes the fraction through datetime.fromisoformat, which discards digits beyond six, and handle() uses that value for ordering and build timestamps. Repro: python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb --test R05. I’m checking another offset and precision variant.

### 14:25:04 Implementer (280)
@Spec tester Wave 2 reproduced R5/R13 on f7c7fd4. Fix fd21eebbc624e31821cf2864b93768b29a4a1c69 passed all 23 wave‑1 checks and all 7 available wave‑2 checks; capture replay was skipped. /tmp/dossier-r8-wave2-fd21.log contains the exact-commit receipt.

### 14:25:04 Implementer (501)
@Reviewer R5/R13 reproduced on the candidate. Fix fd21eebbc624e31821cf2864b93768b29a4a1c69 preserves every fractional digit, compares absolute instants across offsets, and returns the original precision in build timestamps. Both the picosecond regression and a cross-year offset variant failed before the fix and pass after it. The fix is in /tmp/dossier-r8-stage1-fixes; the shared checkout remains at the reviewed commit. Both acceptance waves are running on the fix.

### 14:25:04 Implementer (476)
@Coordinator R5/R13 fix fd21eebbc624e31821cf2864b93768b29a4a1c69 is ready in /tmp/dossier-r8-stage1-fixes. Wave 1 passed 23 checks, and wave 2 passed 7 with one optional capture replay skipped. The submitted commit failed the one-picosecond and cross-year offset clock regressions; the fix passes both. Receipts: /tmp/dossier-r8-wave1-fd21.log and /tmp/dossier-r8-wave2-fd21.log. The shared checkout stays on the reviewed commit until the verdict.

### 14:26:04 Spec tester (489)
@Coordinator Independent exact-commit acceptance confirmed for fd21eebbc624e31821cf2864b93768b29a4a1c69. Wave 1 passed 23 HTTP checks plus the tracked-package check. Wave 2 passed all 7 available checks, including R5/R13 picosecond ordering and timestamp precision. R19 real-response replay was skipped pending capture. Receipts: /home/hark/band-work/spec-tester-run8/stage1/wave1-fd21eeb.log and /home/hark/band-work/spec-tester-run8/stage1/wave2-fd21eeb.log.

### 14:26:35 Reviewer (791)
@Implementer Two more blocking findings independently reproduced on f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. R19/R20: when provider search cannot return the cited page and extraction is refused, a two-sentence research citation must fail Appendix A.1/A.2. The API asserted founded_year 2011 for ivory-delta.test (period boundary) and hq_city Lyon for rustic-cobalt.test (exclamation boundary), by selecting a sentence from each unsupported claim. R22/R19/R20: changing only an exported dossier’s headcount to `unrecognized-tier` or founding year to 123 should reject import with 422 and preserve the destination. Both returned 204, and GET asserted the invalid value with the old citation. Both are in the independent receipt under the review scratch directory.

### 14:28:36 Implementer (470)
@Coordinator R19/R20/R22 are fixed on review branch commit 69b589c2560a348d47d78fed05d4627f86dd4e14, which also contains the R5/R13 fix. The full independent probe now passes all seven scenarios, and wave 1 passes 23 checks. Wave 2 passes all seven non-replay checks. Receipts: /tmp/dossier-r8-independent-69b.log, /tmp/dossier-r8-wave1-69b.log and /tmp/dossier-r8-wave2-69b.log. The shared checkout is still at f7c7fd4, pending the verdict.

### 14:28:51 Implementer (733)
@Reviewer R19/R20/R22 fixed in 69b589c2560a348d47d78fed05d4627f86dd4e14 on top of the R5/R13 fix. Research now checks the entire supplied quotation. Import validates field values against each citation and its source in the saved build before replacing state. Your independent script passed all seven scenarios, including research and import-invariants. Wave 1 passed 23 checks, and wave 2 passed seven before running the separate recorded-response replay. Regression tests cover periods, exclamations, quoted questions, out-of-range and valid-but-unsupported values, and a changed citation URL. All eight targeted cases failed before the fix and pass now. Receipt: /tmp/dossier-r8-independent-69b.log.

### 14:28:51 Reviewer (2218)
@Implementer @Spec tester @Coordinator VERDICT 1 f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb REJECT

Clean exact revision. Wave 1 passed 23/23. The isolated report completed, matched the full revision and claimed stage 1 with 122/122 passing in 86.84 s. Wave 2 passed six checks, failed the clock check, and passed the Etsy live-response replay separately. Independent probes passed five groups and failed two.

Blocking R5/R13. Earlier RFC 3339 instants require 422 and unchanged time. Two variants returned 204, one picosecond earlier at the same offset and 0.1 microseconds earlier across +03:00 and −02:00.

Blocking R19/R20. The research claim citation must itself meet Appendix A's single-sentence rule. With unsearchable cited pages and refused extraction, the API asserted Ivory Delta’s 2011 founding from a two-sentence citation separated by a period and Rustic Cobalt’s Lyon HQ from one separated by an exclamation point.

Blocking R22/R19/R20. Invalid state must return 422 and preserve the destination. Changing only one exported value to headcount_range=unrecognized-tier or founded_year=123 returned 204. Each showed up in GET with the old citation.

R25 live: Apple 3/6, 55 units, 104.15 s. Etsy 4/6, 59 units, 127.89 s. Dropbox 3/6, 71 units, 162.28 s. Combined 10/18, 185 units, 18.50 units/correct output. All 17 emitted excerpts were found verbatim after whitespace normalization at their cited URLs. Carried: ranking credited numbers in links or addresses as headcount, used a 2010 URL over gathered 1976 founding evidence, and treated campaign proceeds as company funding. The response capture accounts for 180 of 185 reported units. Five could not be attributed from completed response frames.

Report and exact commands: /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/review-f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb.md
Isolated report: /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/isolated-f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb/report.json
140 redacted Nimble frames and passing Etsy replay bundle: /home/hark/band-work/spec-tester-run8/stage1/replays/f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb

### 14:29:06 Reviewer (573)
@Coordinator Stage 1 review of f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb is complete. I sent the REJECT verdict to all three seats. The isolated harness claimed Stage 1 at 122/122, and the live run scored 10/18 in 185 units. The blocking findings are timestamp precision and ordering (R5/R13), multi-sentence research citations (R19/R20), and import acceptance of invalid values with mismatched citations (R22/R19/R20). Full evidence is in /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/review-f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb.md.

### 14:29:21 Coordinator (574)
@Star Developer 3071 The first stage 1 candidate `f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb` was rejected despite an isolated stage 1 claim at 122/122. Independent review found three blockers: fractional clock ordering, acceptance of multi-sentence research citations, and import accepting invalid values with old citations. The implementer’s follow-up `69b589c2560a348d47d78fed05d4627f86dd4e14` passed wave 1, available wave 2 checks, and all seven probe groups. I requested its exact-commit submission for independent recheck. Stage 2 remains unopened.

### 14:29:36 Implementer (318)
@Spec tester The fix for all three verdict findings is promoted at 69b589c2560a348d47d78fed05d4627f86dd4e14. Please send the post-verdict TESTS UPDATED command once the period/exclamation, altered-field import and offset/fraction findings are incorporated; I’ll run it on the exact commit.

### 14:29:36 Coordinator (470)
@Implementer Stage 1's first exact verdict is now in /home/hark/band-work/dossier-stage-1-handoff-run8.md. Promote 69b589c2560a348d47d78fed05d4627f86dd4e14 in the clean shared checkout and send CANDIDATE 1 69b589c2560a348d47d78fed05d4627f86dd4e14 with its exact wave 1 receipt. Measure live R25 on the same subjects against your 8/18 baseline and send those measurements when available. The Etsy capture for the R19 replay is in the handoff.

### 14:30:22 Implementer (381)
@Coordinator Promotion is complete. Main is clean at 69b589c2560a348d47d78fed05d4627f86dd4e14. A fresh run after promotion passed wave 1 (23/23) and wave 2 with the Etsy replay (8/8). The live comparison is running. The implementer handoff requires the spec tester’s post-REJECT TESTS UPDATED before the formal replacement candidate; I’ve requested it.

### 14:30:37 Spec tester (755)
@Implementer @Coordinator TESTS UPDATED 1 /home/hark/band-work/spec-tester-run8/stage1/wave2.py
Run `python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit 69b589c2560a348d47d78fed05d4627f86dd4e14 --replay /home/hark/band-work/spec-tester-run8/stage1/replays/f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb/etsy-wave2-bundle.json`. New tests: R05/R13 clock rejects an earlier instant at the same or a different offset and preserves the stored instant. R19/R20 research claim must itself be a single sentence (period and exclamation cases). R22/R19/R20 invalid import rejects out-of-range values and a citation mismatch while preserving destination data. Full exact-commit run is underway.

### 14:30:52 Spec tester (374)
@Implementer All three regressions are incorporated. Run `python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit 69b589c2560a348d47d78fed05d4627f86dd4e14 --replay /home/hark/band-work/spec-tester-run8/stage1/replays/f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb/etsy-wave2-bundle.json`. The independent run on that commit is underway.

### 14:30:52 Spec tester (591)
@Coordinator @Implementer Independent post-verdict acceptance: 69b589c2560a348d47d78fed05d4627f86dd4e14 passed all 11 wave-2 checks, including the Etsy live-response replay. Research served both malformed claims and both were excluded. All three state mutations were tried and rejected. All three new regression groups reproduced against f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb. Receipts: /home/hark/band-work/spec-tester-run8/stage1/wave2-69b589c.log and /home/hark/band-work/spec-tester-run8/stage1/reject-regressions-f7c7fd4.log.

### 14:30:52 Coordinator (337)
@Implementer The spec tester has now sent TESTS UPDATED 1 to both of us. Please submit CANDIDATE 1 69b589c2560a348d47d78fed05d4627f86dd4e14 with your exact wave 1 receipt so independent review can begin while updated wave 2 and live runs finish. Handoff: /home/hark/band-work/dossier-stage-1-handoff-run8.md.

### 14:33:39 Implementer (817)
@Coordinator Main is clean at 69b589c2560a348d47d78fed05d4627f86dd4e14. The exact-commit wave‑1 receipt is /tmp/dossier-r8-main-wave1-69b.log (23/23). Wave 2 passed 8/8 including the supplied Etsy replay; the reviewer’s seven independent regression groups also passed. R25 held at 8/18 supported correct fields. Apple 2/6 (legal name and HQ), 16 units, 34.05s. Dropbox 3/6 (HQ, co-CEO, founding), 69 units, 82.59s. Etsy 3/6 (HQ, CEO, founding), 72 units, 227.48s. Together: 157 units, 19.63 per correct field, down from 207 and 25.88; all 16 emitted excerpts matched the stored provider text. No live tuning. Public responses: /tmp/dossier-r8-impl-live-69b.jsonl. The formal candidate is pending the post-REJECT TESTS UPDATED gate; all available checks and the one live pass are complete.

### 14:33:39 Implementer (638)
@Reviewer R5/R13 is fixed in fd21eebbc624e31821cf2864b93768b29a4a1c69 by preserving fractional digits and ordering absolute instants. R19/R20 and R22/R19/R20 are fixed in 69b589c2560a348d47d78fed05d4627f86dd4e14 by validating entire research quotations and checking each imported value against its citation and saved source. Main has been fast-forwarded to 69b589c. All seven independent probe groups passed, including research and import-invariants; wave 1 passed 23, wave 2 passed seven plus the independent Etsy replay. Your isolated report on the preceding commit remains the reference for that commit.

### 14:33:54 Coordinator (734)
@Reviewer REVIEW 1 69b589c2560a348d47d78fed05d4627f86dd4e14. Handoff: /home/hark/band-work/dossier-stage-1-handoff-run8.md. Changes since the rejected commit: R5/R13 exact clock ordering, R19/R20 whole research citation validation, and R22/R19/R20 imported-value/citation validation. Exact wave 1 verified 23/23 and spec tester's updated wave 2 passed 11/11. Verify the fixes and rerun the required isolated claim and R25 live checks for this exact commit. Implementer held 8/18 with reduced spend; compare your run with your fixed-set 10/18 baseline and include counts, measured spend and elapsed time. Send VERDICT 1 69b589c2560a348d47d78fed05d4627f86dd4e14 ACCEPT|REJECT to all three seats together.

### 14:34:09 Implementer (2255)
@Coordinator CANDIDATE 1 69b589c2560a348d47d78fed05d4627f86dd4e14

Main is clean at the candidate. Wave 1 passed 23/23. Updated wave 2 passed 11/11 with zero skips, including the three verdict regressions and the Etsy response replay. Independent reviewer scenarios passed 7/7. Commands: `python3 /home/hark/band-work/spec-tester-run8/stage1/acceptance.py --commit 69b589c2560a348d47d78fed05d4627f86dd4e14` and `python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit 69b589c2560a348d47d78fed05d4627f86dd4e14 --replay /home/hark/band-work/spec-tester-run8/stage1/replays/f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb/etsy-wave2-bundle.json`. Receipts: /tmp/dossier-r8-main-wave1-69b.log, /tmp/dossier-r8-updated-wave2-69b.log, /tmp/dossier-r8-independent-69b.log.

Coverage: R1 clean archive Docker build and RUN.md; R2 provider-free health; R3 fifty in-flight reads; R4 atomic reset and worker fencing; R5 exact fractional time and cross-offset ordering; R6 structured errors and typed validation; R7 accounts and multiple sessions; R8 bearer precedence; R9 host normalization; R10 replay, conflicts and scope; R11 concurrent creation; R12 refresh coalescing; R13 stable fields and exact build timestamps; R14 list filters, ordering and pagination; R15 build timing; R16 Nimble-only operation and provider-free reads; R17 exact search and research schema; R18 actual provider costs, refusal and partial replies; R19 six sole-source fields and Etsy replay; R20 whole-claim sentence boundaries, ambiguity and negation; R21 active-build export fallback; R22 portable replacement with invalid-field/citation rejection; R23 concurrent keys, failures and stale-worker fencing; R24 exact-commit acceptance passed, with replacement verdict and final isolated claim pending.

R25 held at 8/18 supported correct fields against the preceding implementer run’s 8/18. Apple 2/6 at 16 units in 34.05s. Etsy 3/6 at 72 units in 227.48s. Dropbox 3/6 at 69 units in 82.59s. Total 157 units versus 207 previously, or 19.63 versus 25.88 per correct field. All 16 returned excerpts matched stored provider text. Headcount and funding interpretation remain carried quality issues. Public measurement: /tmp/dossier-r8-impl-live-69b.jsonl.

### 14:36:25 Reviewer (971)
@Implementer Two blocking edge classes on 69b589c2560a348d47d78fed05d4627f86dd4e14; all three prior regressions now pass. R19/R20: the API returned unknown for two otherwise valid single-sentence research citations whose served page prose starts with an uppercase label: “CEO: Etta Navarro is chief executive of Sable Ridge.” and “HQ: Copper Lantern is headquartered in Basel.” The cited pages were unsearchable and extracts refused to isolate the research claim. excerpts() runs prose() on an excerpt and the header regex treats uppercase CEO/HQ as capitalised header words. R5: after reset to the second before a known leap second, the clock rejected both RFC 3339 §5.8 examples 1990-12-31T23:59:60Z and 1990-12-31T15:59:60-08:00 with 422. Each is a valid forward move requiring 204. Repro: bash /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/mock_checks.sh dossier-review-run8:69b589c research-labeled-prose (or clock-leap-seconds).

### 14:37:56 Reviewer (575)
@Implementer The exact-candidate R25 comparator also dropped from 10/18 to 9/18. Apple held 3/6 and Dropbox held 3/6. Etsy dropped from 4/6 to 3/6 because its legal name became unknown. This run used 193 units in 167.99 s. The current capture shows an uppercase ETSY, INC. legal-entity snippet, which does not meet Appendix A.4's exact Inc. suffix; the preceding run had a qualifying research quotation. I have no evidence that the citation fix itself caused the live provider evidence to differ. The handoff gates on the measured fixed-set drop.

### 14:38:57 Reviewer (491)
@Coordinator I sent the REJECT verdict for 69b589c2560a348d47d78fed05d4627f86dd4e14 to all three seats. The prior three regressions pass and the isolated 122/122 run claimed Stage 1. Valid leap-second moves and labeled research citations still fail, and the fixed-set live result fell from 10/18 to 9/18, with 193 units in 167.99 s. The full evidence is at /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/review-69b589c2560a348d47d78fed05d4627f86dd4e14.md.

### 14:38:57 Reviewer (2343)
@Implementer @Spec tester @Coordinator VERDICT 1 69b589c2560a348d47d78fed05d4627f86dd4e14 REJECT

All three prior regressions passed. Exact clean HEAD, wave 1 23/23, updated wave 2 11/11 including Etsy replay. The isolated report matched the full revision, completed, and claimed stage 1 at 122/122 in 84.70 s. Independent probes passed seven groups and failed two.

Blocking R5. RFC 3339 §5.8 lists a known leap second in UTC and at −08:00. After resetting to the second before it, both 1990-12-31T23:59:60Z and 1990-12-31T15:59:60-08:00 returned 422 instead of 204. https://www.rfc-editor.org/rfc/rfc3339#section-5.8

Blocking R19/R20. The candidate left the CEO and HQ unknown for two valid research-only single sentences starting with uppercase labels, “CEO: Etta Navarro is chief executive of Sable Ridge.” and “HQ: Copper Lantern is headquartered in Basel.” The unsearchable cited pages and refused extracts isolated claim handling. The header test discarded both prose sentences.

Blocking R25. Fixed set moved from 10/18 to 9/18, losing Etsy’s legal name. The candidate accepts the qualifying quotation from the first run when given it offline. The latest captured legal-entity search excerpt spells the suffix INC., which Appendix A.4 does not allow. The measured drop is established; a code-caused change in live evidence was not established. Implementer held its separate 8/18 baseline.

Live Apple 3/6, 53 units, 120.97 s. Etsy 3/6, 70 units, 167.99 s. Dropbox 3/6, 70 units, 131.50 s. Combined 193 units, 167.99 s, 21.44 units per correct field; all 16 citations were verified verbatim at their URLs. The ledger reconciles 187 units in completed provider responses and six extract attempts without a completed response. Carried: other-venture founding year, headcounts sourced from an address or contract section, and funding without lifetime equity support.

Report and reproduction: /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/review-69b589c2560a348d47d78fed05d4627f86dd4e14.md
Isolated JSON: /home/hark/band-work/checks/reviewer-s1-run8-RIt0SqNT/isolated-69b589c2560a348d47d78fed05d4627f86dd4e14/report.json
154 redacted capture frames: /home/hark/band-work/spec-tester-run8/stage1/replays/69b589c2560a348d47d78fed05d4627f86dd4e14

### 14:39:27 Coordinator (465)
@Star Developer 3071 The second stage 1 candidate `69b589c2560a348d47d78fed05d4627f86dd4e14` passed the three prior regressions and the isolated harness again claimed stage 1 at 122/122. It was rejected for leap-second clock handling, valid labeled research citations being discarded, and a live score drop from 10/18 to 9/18. The live drop coincided with different provider evidence. The team is addressing those findings before stage 2 opens.

### 14:39:27 Coordinator (703)
@Implementer @Spec tester @Reviewer The second rejection is recorded in /home/hark/band-work/dossier-stage-1-handoff-run8.md. R5 and R19/R20 have two REJECT rounds each. For R25, keep the fixed live subjects and recover the reviewer reference of 10/18 while holding the implementer reference of 8/18. Replay may diagnose provider variation, and the live result remains the gate. Implementer, prepare the general fixes and submit the exact wave-1-passing commit promptly. Spec tester, update the verdict regressions in parallel. Reviewer, end your turn after preparation and I’ll dispatch the exact next candidate.

### 14:39:42 Reviewer (298)
@Coordinator Ready for the next exact revision. The leap-second and labeled-research repros, the prior Etsy replay, and the fixed-set live runner are ready. I’ll apply the 10/18 reviewer and 8/18 implementer references with unchanged scoring. Replay is diagnostic only.

### 14:40:28 Implementer (601)
@Coordinator @Spec tester The shared checkout is clean at 0778d05d2208df2363fdafb4a87a731c29a1d028. It handles leap seconds through the image’s IANA table and preserves acronym-labeled quotations and prose. Research now prioritizes direct company-wide statements, gathers another source for weak matches and shares extraction slots across unresolved fields. New regression cases failed on 69b589c and pass on this revision. Live, acceptance and independent probes are running. Please send the post-verdict TESTS UPDATED command when available.

### 14:40:43 Spec tester (912)
@Implementer @Coordinator TESTS UPDATED 1 /home/hark/band-work/spec-tester-run8/stage1/wave2.py
Run `python3 /home/hark/band-work/spec-tester-run8/stage1/wave2.py --commit 0778d05d2208df2363fdafb4a87a731c29a1d028 --replay /home/hark/band-work/spec-tester-run8/stage1/replays/f7c7fd46f6c39b3641267cd13c7fe09e6e4e4aeb/etsy-wave2-bundle.json`. New tests cover R5/R13 leap-second acceptance, ordering and timestamps in UTC and at −08:00, and R19/R20 CEO/HQ research-only labeled single-sentence prose. R25 compares exact-candidate live evidence with the 10/18 reviewer and 8/18 implementer references: `python3 /home/hark/band-work/spec-tester-run8/stage1/r25_live_baseline.py REVIEW_REPORT --commit 0778d05d2208df2363fdafb4a87a731c29a1d028 --implementer-count LIVE_COUNT`. The previous 9/18 reviewer result fails that count check. Replay remains diagnostic.

### 14:41:14 Spec tester (258)
@Implementer The full wave 2 command for 0778d05d2208df2363fdafb4a87a731c29a1d028 and separate R25 command are in the TESTS UPDATED handoff. New offline regressions cover both leap-second offsets and both labeled research fields.

### 14:41:14 Spec tester (584)
@Coordinator @Implementer Independent wave 2 passed 13/13 on 0778d05d2208df2363fdafb4a87a731c29a1d028, including Etsy replay. Both new offline regressions reproduced on 69b589c and passed on 0778d05. The R25 checker accepts the original 10/18 reviewer and 8/18 implementer evidence and rejects the subsequent 9/18 reviewer result. R25 awaits new exact-candidate live evidence. Logs: /home/hark/band-work/spec-tester-run8/stage1/wave2-0778d05.log and /home/hark/band-work/spec-tester-run8/stage1/reject-regressions-69b589c.log.
