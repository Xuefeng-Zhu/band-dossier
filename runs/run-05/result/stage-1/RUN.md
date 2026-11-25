# Dossier Stage 1

Run this command from the stage folder. Docker forwards provider variables from your environment. Set `NIMBLE_API_KEY` for research. Set `NIMBLE_BASE_URL` if your deployment supplies a custom endpoint. Tavily is optional.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-1
```

Check readiness with `curl http://localhost:8080/health`. State lives in memory for the lifetime of the container. The control endpoints allow tests to set the clock and export or restore a snapshot. Treat snapshots as private because they contain password hashes and active session tokens.
