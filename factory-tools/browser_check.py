"""Run the host-installed Chromium probe against an exact committed service."""

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

PROBE = Path(__file__).resolve().with_name("browser_probe.py")
KICKOFF = PROBE.parents[1] / "sf-buildathon-2026"
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


def run(repo, stage, revision, output):
    security = subprocess.check_output(
        ("docker", "info", "--format", "{{json .SecurityOptions}}"), text=True, timeout=30,
    )
    if "name=rootless" not in json.loads(security):
        raise ValueError("the browser check requires rootless Docker")
    if mockweb.config("dossier")["model"]:
        raise ValueError("the browser check requires an isolated mock with no live model proxy")
    if not PROBE.is_file() or PROBE.is_symlink():
        raise ValueError("the host-installed browser probe is missing")

    output.mkdir(mode=0o700)
    suffix = uuid.uuid4().hex[:16]
    network = f"dossier-review-net-{suffix}"
    browser = f"dossier-review-browser-{suffix}"
    service = f"dossier-review-app-{suffix}"
    image = f"dossier-review/app:{suffix}"
    with ExitStack() as cleanup:
        scratch = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="dossier-review-stage-")))
        extract_stage(repo, revision, stage, scratch)
        runner = cli.ensure_runner_image()
        cleanup.callback(driver.remove_image, image)
        driver.build_image(scratch, tag=image)
        driver.ensure_internal_network(network)
        cleanup.callback(remove_network, network)
        internal = subprocess.check_output(
            ("docker", "network", "inspect", "--format", "{{.Internal}}", network),
            text=True, timeout=30,
        )
        if internal.strip() != "true":
            raise ValueError("the browser check network is not internal")

        mock = mockweb.start("dossier", mode=driver.ISOLATED, network=network)
        if mock is None:
            raise ValueError("the organizer mock service is unavailable")
        cleanup.callback(mockweb.stop, mock)
        cleanup.callback(driver.stop, service)
        _, base_url, _ = driver.start_service(
            image, mode=driver.ISOLATED, name=service, network=network, env=mockweb.service_env(mock),
        )
        cleanup.callback(driver.stop, browser)
        result = subprocess.run(
            ("docker", "run", "--rm", "--name", browser, "--network", network,
             "--cpus", "2", "--memory", "3g", "--shm-size", "256m",
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
             "--volume", f"{PROBE}:/browser_probe.py:ro", "--volume", f"{output}:/out",
             runner, "python", "-B", "/browser_probe.py", "--base-url", base_url,
             "--revision", revision, "--output", "/out"),
            check=False, timeout=600,
        )
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--stage", type=int, choices=(2, 3, 4), required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not REVISION.fullmatch(args.revision):
        parser.error("browser check requires a full Git commit ID")
    try:
        return run(args.repo, args.stage, args.revision, args.output)
    except (driver.DockerError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Browser check could not complete: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
