# Dossier Stage 3

From the stage folder, build and run the service with Docker.

```sh
docker build -t dossier-stage-3 .
docker run --name dossier-stage-3 --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-3
```

`GET http://localhost:8080/health` reports readiness. The container listens on
all interfaces. Pass the Nimble key from the environment and leave the base URL unset to
use the live endpoint. The organizer can set the base URL to the mock Nimble service.
Open `http://localhost:8080/` to use the dossier library, evidence and contested fields.
The dossier detail URL returns HTML for `Accept: text/html` and JSON for API
clients. The browser sends bearer tokens and idempotency keys for the required writes.
Nimble rendered extracts provide the visible page text used for candidate evidence.

The service stores an atomic snapshot at `/data/dossier.json` in the container. Restart
the same container with `docker start dossier-stage-3` to recover accounts, dossiers,
history and the change feed. Set `DOSSIER_STATE_PATH` to use another writable path.
The test export and import routes transfer state and accept Stage 1 and Stage 2 exports
without provider traffic. Keep the browser URL unchanged during an upgrade to retain
the browser session. Exports include password hashes, session tokens and research evidence.
Store exports privately and use the unauthenticated test routes only in a trusted environment.
