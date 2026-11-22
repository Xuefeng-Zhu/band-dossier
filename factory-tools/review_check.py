"""Run a host-installed review probe against an exact committed service."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import uuid

TOOLS = Path(__file__).resolve().parent
KICKOFF = TOOLS.parent / "sf-buildathon-2026"
PROBES = {"browser": TOOLS / "browser_probe.py", "currency": TOOLS / "currency_probe.py"}
REVISION = re.compile(r"[0-9a-f]{40}")
sys.path.insert(0, str(KICKOFF))

from harness import cli, docker_driver as driver, mockweb  # noqa: E402


def extract_stage(repo, revision, stage, target):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
    git = ("/usr/bin/git", "-C", str(repo))
    with tempfile.TemporaryFile() as contents:
        subprocess.run(
            (*git, "archive", "--format=tar", f"{revision}:stage-{stage}"),
            env=env, stdout=contents, check=True, timeout=45,
        )
        contents.seek(0)
        with tarfile.open(fileobj=contents, mode="r:") as archive:
            if any(not (entry.isfile() or entry.isdir()) for entry in archive):
                raise ValueError("the committed stage contains a nonregular archive entry")
            archive.extractall(target, filter="data")


def remove_network(network):
    subprocess.run(("docker", "network", "rm", network), check=True, timeout=60)


def start_currency_mock(cleanup, scratch, network, suffix, probe):
    corpus = scratch / "currency-corpus"
    subprocess.run((sys.executable, "-B", str(probe), "corpus", "--output", str(corpus)),
                   check=True, timeout=30)
    tag = f"dossier-review/currency-mock:{suffix}"
    cleanup.callback(driver.remove_image, tag)
    driver.build_image(KICKOFF / "challenges/dossier/web", tag=tag)
    name = f"dossier-review-mock-{suffix}"
    token = uuid.uuid4().hex
    cleanup.callback(driver.stop, name)
    subprocess.run(
        ("docker", "run", "-d", "--name", name, "--network", network,
         "--volume", f"{corpus}:/data/corpus:ro", "--env", "MOCK_ADMIN_TOKEN", tag),
        env={**os.environ, "MOCK_ADMIN_TOKEN": token}, check=True, timeout=120,
    )
    url = f"http://{name}:{mockweb.PORT}"
    return mockweb.MockWeb(name, url, url, token, network, driver.ISOLATED)


def run(operation, repo, stage, revision, output):
    security = subprocess.check_output(
        ("docker", "info", "--format", "{{json .SecurityOptions}}"), text=True, timeout=30,
    )
    if "name=rootless" not in json.loads(security):
        raise ValueError("the review check requires rootless Docker")
    if mockweb.config("dossier")["model"]:
        raise ValueError("the review check requires an isolated mock with no live model proxy")
    probe = PROBES[operation]
    if not probe.is_file() or probe.is_symlink():
        raise ValueError("the host-installed review probe is missing")

    output.mkdir(mode=0o700)
    suffix = uuid.uuid4().hex[:16]
    network = f"dossier-review-net-{suffix}"
    reviewer = f"dossier-review-probe-{suffix}"
    service = f"dossier-review-app-{suffix}"
    image = f"dossier-review/app:{suffix}"
    with ExitStack() as cleanup:
        scratch = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="dossier-review-stage-")))
        source = scratch / "stage"
        source.mkdir()
        extract_stage(repo, revision, stage, source)
        runner = cli.ensure_runner_image()
        cleanup.callback(driver.remove_image, image)
        driver.build_image(source, tag=image)
        driver.ensure_internal_network(network)
        cleanup.callback(remove_network, network)
        internal = subprocess.check_output(
            ("docker", "network", "inspect", "--format", "{{.Internal}}", network),
            text=True, timeout=30,
        )
        if internal.strip() != "true":
            raise ValueError("the review check network is not internal")

        args = []
        env = dict(os.environ)
        docker_env = []
        if operation == "currency":
            mock = start_currency_mock(cleanup, scratch, network, suffix, probe)
            args = ["check", "--mock-url", mock.test_url]
            env["MOCK_ADMIN_TOKEN"] = mock.token
            docker_env = ["--env", "MOCK_ADMIN_TOKEN"]
        else:
            mock = mockweb.start("dossier", mode=driver.ISOLATED, network=network)
            if mock is None:
                raise ValueError("the organizer mock service is unavailable")
            cleanup.callback(mockweb.stop, mock)
        cleanup.callback(driver.stop, service)
        _, base_url, _ = driver.start_service(
            image, mode=driver.ISOLATED, name=service, network=network, env=mockweb.service_env(mock),
        )
        cleanup.callback(driver.stop, reviewer)
        result = subprocess.run(
            ("docker", "run", "--rm", "--name", reviewer, "--network", network,
             "--cpus", "2", "--memory", "3g", "--shm-size", "256m",
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges", *docker_env,
             "--volume", f"{probe}:/review_probe.py:ro", "--volume", f"{output}:/out",
             runner, "python", "-B", "/review_probe.py", *args, "--base-url", base_url,
             "--revision", revision, "--output", "/out"),
            env=env, check=False, timeout=600,
        )
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=PROBES)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--stage", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not REVISION.fullmatch(args.revision):
        parser.error("review check requires a full Git commit ID")
    if args.operation == "browser" and args.stage == 1:
        parser.error("browser checks require Stage 2 or later")
    try:
        return run(args.operation, args.repo, args.stage, args.revision, args.output)
    except (driver.DockerError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Review check could not complete: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
