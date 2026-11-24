# Run the company dossier service

From this folder, build and start the container. Docker forwards provider credentials and endpoint overrides from the calling environment. Set NIMBLE_API_KEY for research.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-1
```

Readiness is available at `GET /health`. The service holds its state in memory. The export and import control endpoints transfer that state between containers.
