# Run Dossier

From this directory, build and start the container with the Nimble credential supplied through your environment.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL dossier-stage-1
```

The service listens on all interfaces. Set NIMBLE_BASE_URL when using a provider test endpoint. The default endpoint is the live Nimble service. GET /health reports readiness. State lives in memory. The control API supports private JSON export and import for state transfer.
