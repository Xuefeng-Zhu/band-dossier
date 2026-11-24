# Dossier service

Run from this directory with the Nimble credential exported in the shell.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-1
```

Leave NIMBLE_BASE_URL unset to use the provider default, or export the URL of a provider reachable from the container. GET /health reports readiness. The service stores data in memory. Use the export and import endpoints to transfer a snapshot.
