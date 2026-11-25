# Dossier Stage 4

From this directory, build and run the single container. Set `NIMBLE_API_KEY`
in your environment before starting it. If you use the organizer mock, also
set `NIMBLE_BASE_URL` to the mock's Nimble endpoint reachable from the container.

```sh
docker build -t dossier-stage-4 .
docker run --name dossier-stage-4 --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-4
```

Open `http://localhost:8080` for the research workspace.
`GET /health` returns `{"status":"ok"}`. The service uses Nimble for search,
rendered extracts and optional research. It accepts this team's Stage 1 and
Stage 2 and Stage 3 exports. Histories, page versions, the change feed and
budgeted batches are available through the authenticated API.

Stop and start the same container to retain its state, or use
`docker restart dossier-stage-4`. The state file and active build journals
live in `/data`. An interrupted build is settled as failed on startup.
Keep exports and the state directory private because they include bearer
sessions, password hashes and gathered evidence.
