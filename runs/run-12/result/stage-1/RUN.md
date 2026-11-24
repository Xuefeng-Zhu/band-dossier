# Run the dossier service

From this directory, build and start the image with Docker. Export your Nimble key before launching it.

```sh
docker build -t dossier-stage-1 . && docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY -e NIMBLE_BASE_URL -e TAVILY_API_KEY -e TAVILY_BASE_URL dossier-stage-1
```

Unset the base URL variables to use provider defaults. Set them to your mock provider endpoints for offline use. Tavily credentials are optional. The process holds state in memory. Its unauthenticated test controls include account export, so bind the published port to localhost for private deployments.
