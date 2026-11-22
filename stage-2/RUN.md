# Run Dossier Stage 2

From this directory, with `NIMBLE_API_KEY` already set in the shell, run:

~~~sh
docker build -t dossier-stage-2 .
docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY dossier-stage-2
~~~

Use `GET http://localhost:8080/health` to check startup. To use the organizer
mock, attach the service container to the mock's Docker network and pass
`-e NIMBLE_BASE_URL=http://web:8080/nimble` with the mock hostname and port.

Open `http://localhost:8080/` to sign up and research a company.

State lives in memory. Take a private snapshot with `GET /_test/export` before
stopping a container. To upgrade from Stage 1, send that service's export to
the Stage 2 `POST /_test/import` endpoint. Keep the browser origin the same
to reuse its existing session during the upgrade.
