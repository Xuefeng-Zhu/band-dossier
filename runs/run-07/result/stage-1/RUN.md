# Company dossiers

From this directory, build and start the service with Docker. The command forwards provider credentials and endpoint settings from the host environment.

```sh
docker build -t company-dossiers . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL company-dossiers
```

Readiness is available at `GET /health`. Research requires a Nimble credential. A configured Tavily account can supply additional search results. If the endpoint is on the host loopback interface, use host networking on Linux so the container can reach the configured address.

The service keeps its state in memory. Use `GET /_test/export` and `POST /_test/import` to transfer state between instances. An export contains password hashes and active session tokens and should be stored privately.
