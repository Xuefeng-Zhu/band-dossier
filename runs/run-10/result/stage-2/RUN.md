# Run Dossier
From this folder run the following with Docker installed. Set NIMBLE_API_KEY in the environment for research. Set NIMBLE_BASE_URL when using a compatible provider endpoint.

```sh
docker build -t dossier-stage-2 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-2
```

GET /health returns the service status. State lives in memory for the lifetime of the container. Treat test exports as secrets because they include active tokens and password hashes.
