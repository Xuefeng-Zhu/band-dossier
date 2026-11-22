# Dossier Stage 2

From the stage folder, build and run the service with Docker.

```sh
docker build -t dossier-stage-2 .
docker run --rm --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-2
```

`GET http://localhost:8080/health` reports readiness. The container listens on
all interfaces. Pass the Nimble key from the environment and leave the base URL unset to
use the live endpoint. The organizer can set the base URL to the mock Nimble service.
Open `http://localhost:8080/` to use the dossier library, evidence and contested fields.
The dossier detail URL returns HTML for `Accept: text/html` and JSON for API
clients. The browser sends bearer tokens and idempotency keys for the required writes.
Nimble rendered extracts provide the visible page text used for candidate evidence.

State is in memory. The test export and import routes transfer complete state between
instances and accept Stage 1 exports without provider traffic. Keep the browser URL
unchanged when replacing Stage 1 with Stage 2 to retain the browser session.
Exports include password hashes, session tokens, and internal research evidence.
Store exports privately and use the unauthenticated test routes only in a trusted environment.
