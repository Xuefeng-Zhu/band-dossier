# Dossier

**Comparison draft.** This branch packages a fresh Band run against the verified build on `main`. The fresh run’s full Band room export is pending. [Verification and comparison](docs/verification.md)

Dossier is a company research service built for the Dossier track of the BAND Dark Factory Buildathon. Enter a company domain to get a profile whose findings link back to supporting excerpts. A three-seat Band Desktop factory built and independently reviewed four successive versions of the service.

## Run Stage 4

Follow the Docker commands, then open `http://localhost:8080/` to sign up and research a company. Live research uses your Nimble API quota. The included Runway response came from the fresh run’s accepted Stage 4. It reached `ready` in 69.1 seconds and reported 78 research units. [Stage 4 run instructions](stage-4/RUN.md) · [Runway response](dossier-runway.com.json)

## Explore the repository

| Path | What to look for |
| --- | --- |
| [Stage 1](stage-1/) | Company profile API, citations and research budget |
| [Stage 2](stage-2/) | Browser interface and competing candidate values |
| [Stage 3](stage-3/) | Executive roles, historical queries and change feed |
| [Stage 4](stage-4/) | Independent-source attribution, investors, batch budgets and provider failure handling |
| [Factory](FACTORY.md) and [mandates](mandates/) | Baseline factory setup and the same three seat mandates used by both runs |
| [Room export](room.json) | Full session export for the verified baseline |
| [Verification](docs/verification.md) | Accepted commits, organizer checks and comparison with the verified build |
| [Submission checklist](docs/submission-checklist.md) | Finish the entrant’s write-up and assemble the judging materials |

The fresh run’s final accepted service revision was `c90b2c33d1b3b925c4d913a388bdb53fb17cd280`. Stage 4 passed 153/153 public organizer checks, 13/13 currency probes, 12/12 Chromium route and viewport captures, and 507/507 independent assertions. [Verification details](docs/verification.md)
