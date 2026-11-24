# Dossier

**Buildathon draft.** The entrant should write the final team introduction and project description before submitting. [Official submission instructions](https://github.com/band-ai/sf-buildathon-2026/blob/704324580f8ac1f893dc2e0a0339b9b3905e7707/docs/participant-guide.md#check-and-submit)

Dossier is a company research service built for the Dossier track of the BAND Dark Factory Buildathon. Enter a company domain to get a profile whose findings link back to supporting excerpts. A three-seat Band Desktop factory built and independently reviewed four successive versions of the service.

## Run Stage 4

Open [the Stage 4 run instructions](stage-4/RUN.md) for the Docker commands. With the container running, open `http://localhost:8080/` to sign up and research a company. Live research uses your Nimble API quota. The included Runway dossier is the verbatim response from a separate live run of the accepted Stage 4. It reached `ready` in about 114 seconds and reported 78 research units. [Runway response](dossier-runway.com.json)

## Explore the repository

| Path | What to look for |
| --- | --- |
| [Stage 1](stage-1/) | Company profile API, citations and research budget |
| [Stage 2](stage-2/) | Browser interface and competing candidate values |
| [Stage 3](stage-3/) | Executive roles, historical queries and change feed |
| [Stage 4](stage-4/) | Independent-source attribution, investors, batch budgets and provider failure handling |
| [Factory](FACTORY.md) and [mandates](mandates/) | Seat responsibilities, setup, delivery protocol and review examples |
| [Room export](room.json) | Full transcript of the Factory v2 Currency run that produced the four accepted stages |
| [Verification](docs/verification.md) | Reproduce the organizer checks and trace the results to accepted commits |
| [Submission checklist](docs/submission-checklist.md) | Finish the entrant’s write-up and assemble the judging materials |

The final accepted service revision was `ce35abb4b6d635e9d6a82cc928c3bf2884f16fa0`. Stage 4 passed 153/153 public organizer checks, 13/13 currency probes, 12/12 Chromium route and viewport captures, and 190/190 independent checks in the judged run. [Verification details](docs/verification.md)
