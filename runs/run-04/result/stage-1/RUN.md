# Company dossiers

From this directory, build and start the service with Docker. The research worker reads the Nimble credential from the environment. Set `NIMBLE_BASE_URL` to use a provider test endpoint. Tavily can serve as a fallback when its credential is available.

```sh
docker build -t company-dossiers . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL company-dossiers
```

`GET /health` reports readiness. State lives in the service process. The unauthenticated `/_test/export` and `/_test/import` endpoints transfer accounts, active sessions, research evidence and replay records, so run the container on a trusted network.
