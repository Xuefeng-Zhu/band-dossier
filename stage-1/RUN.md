# Dossier Stage 1

From the stage folder, build and run the service with Docker.

```sh
docker build -t dossier-stage-1 .
docker run --rm --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-1
```

`GET http://localhost:8080/health` reports readiness. The container listens on
all interfaces. Pass the Nimble key from the environment and leave the base URL unset to
use the live endpoint. The organizer can set the base URL to the mock Nimble service.
Sign up or log in to obtain a bearer token. Dossier creation and refresh run in the
background and require an idempotency key.

State is in memory. The test export and import routes transfer complete state between
instances. Exports include password hashes, session tokens, and internal research evidence.
Store exports privately and use the unauthenticated test routes only in a trusted environment.
