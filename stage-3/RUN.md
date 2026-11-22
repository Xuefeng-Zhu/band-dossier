# Run Dossier Stage 3

From this directory, with `NIMBLE_API_KEY` already set in the shell, run:

~~~sh
docker build -t dossier-stage-3 .
docker run --name dossier-stage-3 -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY dossier-stage-3
~~~

Use `GET http://localhost:8080/health` to check startup. To use the organizer
mock, attach the service container to the mock's Docker network and pass
`-e NIMBLE_BASE_URL=http://web:8080/nimble` with the mock hostname and port.

Open `http://localhost:8080/` to sign up and research a company.

The state and clock survive a restart of the same container. Take a private
snapshot with `GET /_test/export` before replacing a container. To upgrade
from Stage 1 or 2, send that service's export to Stage 3's `POST /_test/import`
endpoint. Keep the browser origin the same to reuse the existing session.
