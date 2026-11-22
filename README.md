# Dossier

**Buildathon draft.** The entrant should write the final team introduction and project description before submitting. [Official submission instructions](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#check-and-submit)

Dossier is a company research service built for the Dossier track of the BAND Dark Factory Buildathon. Enter a company domain to get a profile whose findings link back to supporting excerpts. A three-seat Band Desktop factory built and independently reviewed four successive versions of the service.

## Run Stage 4

Open [the Stage 4 run instructions](stage-4/RUN.md) for the Docker commands. With the container running, open `http://localhost:8080/` to sign up and research a company. Live research uses your Nimble API quota. The included [Runway dossier](dossier-runway.com.json) lets you inspect a live result without making an API call.

## Explore the repository

| Path | What to look for |
| --- | --- |
| [Stage 1](stage-1/) | Company profile API, citations and research budget |
| [Stage 2](stage-2/) | Browser interface and competing candidate values |
| [Stage 3](stage-3/) | Executive roles, historical queries and change feed |
| [Stage 4](stage-4/) | Independent-source attribution, investors, batch budgets and provider failure handling |
| [Factory](FACTORY.md) and [mandates](mandates/) | Seat responsibilities, setup, delivery protocol and review examples |
| [Room export](room.json) | Full transcript of the corrected four-stage Band run |
| [Verification](docs/verification.md) | Reproduce the organizer checks and trace the results to accepted commits |
| [Submission checklist](docs/submission-checklist.md) | Finish the entrant’s write-up and assemble the judging materials |

The final accepted service revision was `6e8c2fc`. Its Stage 4 build passed all 153 organizer checks shipped in the pinned harness. A separate audit passed 13 funding-currency cases on each stage. [Verification details](docs/verification.md)
