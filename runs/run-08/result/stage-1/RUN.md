# Run the dossier API

From this folder, run the following command with the provider environment variables supplied by your deployment.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-1
```

The API listens on port 8080. Check readiness with `curl http://localhost:8080/health`. Nimble supplies search, extract and research. Tavily can supply fallback search and extraction when configured. Data stays in memory and can be transferred through the export and import endpoints.
