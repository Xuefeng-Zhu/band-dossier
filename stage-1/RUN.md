# Dossier Stage 1

From this directory, build and run the single container. Set `NIMBLE_API_KEY`
in your environment before starting it. If you use the organizer mock, also
set `NIMBLE_BASE_URL` to the mock's Nimble endpoint reachable from the container.

```sh
docker build -t dossier-stage-1 .
docker run --rm --cpus 2 --memory 3g -p 8080:8080 \
  -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-1
```

`GET /health` returns `{"status":"ok"}`. The service uses Nimble for
research and keeps state in memory. Fixture reset, clock, export and import
are enabled as specified. Keep exports private because they include bearer
sessions, password hashes and the evidence gathered by each build.
