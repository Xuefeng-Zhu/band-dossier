# Run the company dossier service

From this directory, build and start the image with Docker. Set your Nimble credential in the shell for company research.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY dossier-stage-1
```

The service listens on all interfaces. Check readiness with `curl http://localhost:8080/health`. For a local WebRouter provider endpoint, also pass `-e NIMBLE_BASE_URL` with the endpoint set in the host environment. To enable the optional Tavily fallback, pass `-e TAVILY_API_KEY` and, when configured, `-e TAVILY_BASE_URL`.

State lives in the container process. The unauthenticated test controls can replace or export it, including session tokens and password hashes. Keep the service and exports within the intended test environment.
