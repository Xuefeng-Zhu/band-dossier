"""Request a stage-scoped Git commit or isolated verification from the host."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid


WORK = Path(__file__).resolve().parents[1]
CONTINUATION_REPO = WORK / "band-work" / "result"
FRESH_REPO = WORK / "band-work" / "dossier-full-result"
RETRY_REPO = WORK / "band-work" / "dossier-full-retry"
CURRENCY_REPO = WORK / "band-work" / "dossier-full-currency"
REPO = CONTINUATION_REPO
REPORT_PREFIXES = {
    CONTINUATION_REPO: "dossier",
    FRESH_REPO: "dossier-fresh",
    RETRY_REPO: "dossier-retry",
    CURRENCY_REPO: "dossier-currency",
}
CHECKS = WORK / "band-work" / "checks"
KICKOFF = WORK / "sf-buildathon-2026"
QUEUE = ".band-continuation-operations"
STAGES = (2, 3, 4)
FRESH_STAGES = (1, *STAGES)
REVIEW_OPERATIONS = ("currency", "browser")
OPERATIONS = ("commit", "check", *REVIEW_OPERATIONS)
ACCEPTED_STAGE_ONE = "7d73e7b64b1252f2ba8590a36e092d23f076a67c"
REQUEST_ID = re.compile(r"[0-9a-f]{32}")
REVISION = re.compile(r"[0-9a-f]{40}")
GIT = ("/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")


def git(*args):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
    return subprocess.run(
        (*GIT, "-C", str(REPO), *args), capture_output=True, text=True,
        errors="surrogateescape", check=True, timeout=45, env=environment,
    ).stdout.rstrip("\n")


def verify_stage_files(folder):
    stage = REPO / folder
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError(f"{folder} must be a regular directory")
    for path in stage.rglob("*"):
        mode = path.lstat().st_mode
        if (not (stat.S_ISDIR(mode) or stat.S_ISREG(mode))
                or path.name == ".git" or not path.name.isprintable()):
            raise ValueError(f"unexpected stage entry: {str(path.relative_to(REPO))!r}")


def clean_paths(*paths):
    return not git("status", "--porcelain", "--untracked-files=all", "--ignored=matching", "--", *paths)


def verify_prerequisites(stage):
    if REPO == CONTINUATION_REPO:
        git("merge-base", "--is-ancestor", ACCEPTED_STAGE_ONE, "HEAD")
        if git("rev-parse", f"{ACCEPTED_STAGE_ONE}:stage-1") != git("rev-parse", "HEAD:stage-1"):
            raise ValueError("the accepted Stage 1 tree must stay unchanged")
    previous = [f"stage-{number}" for number in range(1, stage)]
    for folder in previous:
        if git("cat-file", "-t", f"HEAD:{folder}") != "tree":
            raise ValueError(f"{folder} must be committed before starting Stage {stage}")
        verify_stage_files(folder)
    if previous and not clean_paths(*previous):
        raise ValueError("earlier stage folders must stay unchanged")


def staged_paths():
    return git("diff", "--cached", "--no-renames", "--name-only", "-z").split("\0")[:-1]


def commit_stage(stage, folder, message):
    if not isinstance(message, str) or not 1 <= len(message) <= 160 or not message.isprintable():
        raise ValueError("commit message must be a single printable line")
    if any(os.path.lexists(REPO / f"stage-{later}") for later in STAGES if later > stage):
        raise ValueError("cannot commit an earlier stage after a later folder exists")
    if any(not path.startswith(folder + "/") for path in staged_paths()):
        raise ValueError("Git index contains changes outside the requested stage")
    git("add", "-A", "--", folder)
    paths = staged_paths()
    if not paths or any(not path.startswith(folder + "/") for path in paths):
        raise ValueError("commit requires staged changes confined to the requested stage")
    git("-c", "user.name=Implementer", "-c", "user.email=implementer@band-factory.invalid",
        "commit", "--no-gpg-sign", "-m", message, "--", folder)
    return {"ok": True, "revision": git("rev-parse", "HEAD"), "paths": paths}


def verify_check_checkout(stage, revision):
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ValueError("check requires a full Git commit ID")
    if git("rev-parse", "HEAD") != revision or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("check requires the named revision in a clean checkout")
    if not clean_paths(*(f"stage-{number}" for number in range(1, stage + 1))):
        raise ValueError("check requires clean stage folders including ignored paths")


def check_stage(stage, token, revision):
    verify_check_checkout(stage, revision)
    track_name = REPORT_PREFIXES[REPO]
    report_dir = CHECKS / f"{track_name}-stage-{stage}-{token}"
    log_path = report_dir.with_suffix(".log")
    with log_path.open("x") as log:
        result = subprocess.run(
            (str(KICKOFF / ".venv/bin/python"), "-m", "harness", "run", "--track", "dossier",
             "--repo", str(REPO), "--stage", str(stage), "--mode", "isolated", "--out", str(report_dir)),
            cwd=KICKOFF, stdout=log, stderr=subprocess.STDOUT, timeout=7200,
        )
    if git("rev-parse", "HEAD") != revision or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError(f"checkout changed during the check; see {log_path}")
    if not clean_paths(*(f"stage-{number}" for number in range(1, stage + 1))):
        raise ValueError(f"a stage folder changed during the check; see {log_path}")
    return {"ok": result.returncode == 0, "exit_code": result.returncode, "revision": revision,
            "report": str(report_dir / "report.json"), "log": str(log_path)}


def verify_review_operation(operation, stage):
    if operation in REVIEW_OPERATIONS and REPO != CURRENCY_REPO:
        raise ValueError("supplemental review checks require --currency-run")
    if operation == "browser" and stage == 1:
        raise ValueError("browser checks require Stage 2 or later")


def check_with_probe(operation, stage, token, revision):
    verify_check_checkout(stage, revision)
    report_dir = CHECKS / f"{REPORT_PREFIXES[REPO]}-{operation}-{stage}-{token}"
    log_path = report_dir.with_suffix(".log")
    helper = Path(__file__).resolve().with_name("review_check.py")
    with log_path.open("x") as log:
        result = subprocess.run(
            (str(KICKOFF / ".venv/bin/python"), "-B", str(helper), operation, "--repo", str(REPO),
             "--stage", str(stage), "--revision", revision, "--output", str(report_dir)),
            cwd=KICKOFF, stdout=log, stderr=subprocess.STDOUT, timeout=7200,
        )
    verify_check_checkout(stage, revision)
    report = report_dir / "report.json"
    evidence = json.loads(report.read_text()) if report.is_file() else {}
    passed = (result.returncode == 0 and evidence.get("revision") == revision
              and evidence.get("state") == "completed" and evidence.get("passed") is True)
    return {"ok": passed, "exit_code": result.returncode,
            "revision": revision, "report": str(report) if report.is_file() else None, "log": str(log_path)}


def process(token, request):
    if not isinstance(request, dict) or set(request) != {"operation", "stage", "value"}:
        raise ValueError("invalid operation request")
    operation, stage, value = request["operation"], request["stage"], request["value"]
    if operation not in OPERATIONS or type(stage) is not int or stage not in STAGES:
        raise ValueError("request must be a commit or an isolated verification for a stage in this run")
    verify_review_operation(operation, stage)
    folder = f"stage-{stage}"
    verify_stage_files(folder)
    verify_prerequisites(stage)
    if operation == "commit":
        outcome = commit_stage(stage, folder, value)
    elif operation == "check":
        outcome = check_stage(stage, token, value)
    else:
        outcome = check_with_probe(operation, stage, token, value)
    return {"stage": stage, **outcome}


def read_request(queue_fd, entry):
    fd = os.open(entry, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=queue_fd)
    with os.fdopen(fd, "rb") as incoming:
        if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
            raise ValueError("request must be a regular file")
        raw = incoming.read(4097)
        if len(raw) > 4096:
            raise ValueError("request is too large")
        return json.loads(raw)


def serve():
    queue_fd = os.open(REPO / QUEUE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    completed = set()
    try:
        fcntl.flock(queue_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            entries = set(os.listdir(queue_fd))
            for entry in sorted(entries):
                token, _, suffix = entry.partition(".")
                if suffix != "request.json" or not REQUEST_ID.fullmatch(token) or token in completed:
                    continue
                completed.add(token)
                final = f"{token}.response.json"
                if final in entries:
                    continue
                try:
                    response = process(token, read_request(queue_fd, entry))
                except subprocess.CalledProcessError as error:
                    response = {"ok": False, "error": (error.stderr or error.stdout or str(error))[-4000:]}
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    response = {"ok": False, "error": str(error)}
                name = f"{token}.response.tmp"
                try:
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=queue_fd)
                    with os.fdopen(fd, "w", encoding="utf-8") as outgoing:
                        json.dump(response, outgoing)
                    os.rename(name, final, src_dir_fd=queue_fd, dst_dir_fd=queue_fd)
                except OSError as error:
                    print(f"Could not return operation {token}: {error}", flush=True)
            time.sleep(0.5)
    finally:
        os.close(queue_fd)


def main():
    global REPO, STAGES
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--fresh-run", dest="repo", action="store_const", const=FRESH_REPO,
                        help="target the first fresh-run repository")
    target.add_argument("--retry-run", dest="repo", action="store_const", const=RETRY_REPO,
                        help="target the separate retry repository")
    target.add_argument("--currency-run", dest="repo", action="store_const", const=CURRENCY_REPO,
                        help="target the fresh Dossier currency run")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("serve")
    subparsers.add_parser("status").add_argument("value")
    for action in OPERATIONS:
        operation = subparsers.add_parser(action)
        operation.add_argument("stage", type=int, choices=FRESH_STAGES)
        operation.add_argument("value")
    args = parser.parse_args()
    if args.repo:
        REPO = args.repo
        STAGES = FRESH_STAGES
    if args.action in OPERATIONS and args.stage not in STAGES:
        parser.error("stage is outside the configured run")
    if args.action in REVIEW_OPERATIONS:
        try:
            verify_review_operation(args.action, args.stage)
        except ValueError as error:
            parser.error(str(error))
    if args.action == "serve":
        serve()
        return
    if Path.cwd().resolve() != REPO:
        parser.error("run from the Dossier result checkout root")
    queue = REPO / QUEUE
    if args.action == "status":
        if not REQUEST_ID.fullmatch(args.value):
            parser.error("invalid operation ID")
        response = queue / f"{args.value}.response.json"
        print(response.read_text() if response.exists() else "pending")
        return
    token = uuid.uuid4().hex
    temporary = queue / f"{token}.tmp"
    with temporary.open("x") as outgoing:
        json.dump({"operation": args.action, "stage": args.stage, "value": args.value}, outgoing)
    temporary.rename(queue / f"{token}.request.json")
    print(token)


if __name__ == "__main__":
    main()
