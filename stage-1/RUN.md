# Run Dossier Stage 1

From this directory, with `NIMBLE_API_KEY` already set in the shell, run:

~~~sh
docker build -t dossier-stage-1 .
docker run --rm -p 8080:8080 -e PORT=8080 -e NIMBLE_API_KEY dossier-stage-1
~~~

Use `GET http://localhost:8080/health` to check startup. To use the organizer
mock, attach the service container to the mock's Docker network and pass
`-e NIMBLE_BASE_URL=http://web:8080/nimble` with the mock hostname and port.

State lives in memory. Take a private snapshot with `GET /_test/export` before
stopping a container if you need to transfer its data to another instance.
