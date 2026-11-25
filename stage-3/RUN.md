# Dossier Stage 3

From this directory, build and run the single container. Set `NIMBLE_API_KEY`
in your environment before starting it. If you use the organizer mock, also
set `NIMBLE_BASE_URL` to the mock's Nimble endpoint reachable from the container.

```sh
docker build -t dossier-stage-3 .
docker run --name dossier-stage-3 --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-3
```

Open `http://localhost:8080` for the research workspace.
`GET /health` returns `{"status":"ok"}`. The service uses Nimble for search,
rendered extracts and optional research. It accepts this team's Stage 1 and
Stage 2 exports. Histories, page versions and the change feed are available
through the authenticated API.

Stop and start the same container to retain its state, or use
`docker restart dossier-stage-3`. The state file lives at
`/data/state.json` in the container. Keep exports and the state file private
because they include bearer sessions, password hashes and gathered evidence.
