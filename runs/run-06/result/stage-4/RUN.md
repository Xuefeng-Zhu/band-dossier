# Run Dossier

From this directory, build the image and start the service with your provider credentials supplied in the environment.

```sh
docker build -t dossier-stage-4 . && docker run --name dossier-stage-4 -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-4
```

Open `http://localhost:8080/` to use the dossier workspace.

Check readiness with `curl http://localhost:8080/health`. Nimble alone supports research. Tavily is optional. The container stores accounts, sessions, clock, build evidence, change history, batch ownership and provider spending in SQLite. A new container starts empty. Stopping and restarting the same container restores its state. Interrupted builds end failed and retain their previous fields. SQLite records paid-call reservations before dispatch so their costs survive an abrupt stop. Treat control endpoint exports as private because they contain active bearer tokens and password hashes.
