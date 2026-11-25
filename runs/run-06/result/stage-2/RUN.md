# Run Dossier

From this directory, build the image and start the service with your provider credentials supplied in the environment.

```sh
docker build -t dossier-stage-2 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-2
```

Open `http://localhost:8080/` to use the dossier workspace.

Check readiness with `curl http://localhost:8080/health`. Nimble alone supports research. Tavily is optional. The container stores state in memory and starts empty. Treat control endpoint exports as private because they contain active bearer tokens and password hashes.
