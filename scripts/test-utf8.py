#!/usr/bin/env python3
"""Test an existing sava-openjdk image and its exported scratch runtime."""

import argparse
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios
import time
import uuid

UNICODE = "caf\u00e9-\u20ac-\U0001f680-\ufffd"
ASCII = "plain-ASCII-123"
OK = b"UTF8_PROBE_OK"
ENCODING_FAILURE = b"UTF8_PROBE_ENCODING_FAILURE"
# Docker connection/configuration infrastructure only; do not forward user secrets.
INFRA_ENV = (
    "PATH", "HOME", "TMPDIR", "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT",
    "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_API_VERSION", "XDG_RUNTIME_DIR",
)


class TestFailure(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Existing local sava-openjdk image (never removed)")
    parser.add_argument("--platform", choices=("linux/amd64", "linux/arm64"))
    parser.add_argument("--timeout", type=float, default=120,
                        help="Seconds allowed per Docker operation (default: 120)")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    env = {key: os.environ[key] for key in INFRA_ENV if key in os.environ}
    env.update(LANG="C.UTF-8", LC_ALL="C.UTF-8", TERM="xterm")
    root = Path(__file__).resolve().parent.parent
    run_id = uuid.uuid4().hex
    targets = ("direct", "scratch-runtime")
    images = [f"sava-openjdk-utf8-test:{run_id}-{target}" for target in targets]
    containers = set()
    platform = ["--platform", args.platform] if args.platform else []

    def command(argv, label, timeout=None, stream=False):
        try:
            result = subprocess.run(argv, env=env, stdout=None if stream else subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=timeout or args.timeout)
        except subprocess.TimeoutExpired as exc:
            raise TestFailure(f"{label}: timed out") from exc
        except OSError as exc:
            raise TestFailure(f"{label}: could not start Docker") from exc
        if result.returncode:
            # Docker output may contain caller configuration; keep it out of reports.
            raise TestFailure(f"{label}: Docker exited {result.returncode}")
        return result.stdout

    def stop_own_container(name):
        try:
            subprocess.run(["docker", "rm", "--force", name], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def probe(image, mode, negative=False):
        name = f"sava-openjdk-utf8-{run_id}-{uuid.uuid4().hex[:8]}"
        containers.add(name)
        argv = ["docker", "run", "--rm", "--name", name, "--network", "none", *platform,
                "--env", f"UTF8_PROBE_TEXT={UNICODE}", "--env", f"UTF8_PROBE_ASCII={ASCII}"]
        if negative:
            argv += ["--env", "LANG=C", "--env", "LC_ALL=C"]
        console = mode.startswith("console-")
        if console:
            argv += ["--interactive", "--tty"]
        argv += [image, mode]
        process = None
        master = slave = None
        completed = False
        try:
            if not console:
                process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                try:
                    output, _ = process.communicate(timeout=args.timeout)
                except subprocess.TimeoutExpired as exc:
                    raise TestFailure("probe timed out") from exc
            else:
                master, slave = pty.openpty()
                process = subprocess.Popen(
                    argv, env=env, stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True,
                    preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
                )
                os.close(slave)
                slave = None
                output = bytearray()
                sent = False
                deadline = time.monotonic() + args.timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TestFailure("console probe timed out")
                    readable, _, _ = select.select([master], [], [], min(remaining, 0.2))
                    if readable:
                        try:
                            chunk = os.read(master, 4096)
                        except OSError as exc:
                            if exc.errno != errno.EIO:
                                raise
                            chunk = b""
                        if not chunk:
                            break
                        output.extend(chunk)
                        if not sent and b"PASSWORD_READY" in output:
                            text = UNICODE if mode == "console-unicode" else ASCII
                            os.write(master, (text + "\n").encode("utf-8"))
                            sent = True
                    elif process.poll() is not None:
                        break
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
                if not sent:
                    raise TestFailure("console prompt was not reached")
                if text.encode("utf-8") in output:
                    raise TestFailure("console password was echoed")
            completed = True
            if negative:
                if process.returncode != 42 or ENCODING_FAILURE not in output:
                    raise TestFailure("C-locale control did not detect non-UTF-8 native encoding")
            elif process.returncode != 0 or OK not in output:
                raise TestFailure(f"probe failed (exit {process.returncode})")
        finally:
            if not completed:
                stop_own_container(name)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            if master is not None:
                os.close(master)
            if slave is not None:
                os.close(slave)
            if completed:
                containers.discard(name)

    try:
        command(["docker", "image", "inspect", args.image], "base image lookup")
        builder = command(["docker", "context", "show"], "Docker context lookup").decode("utf-8").strip()
        if not builder:
            raise TestFailure("Docker context lookup returned no context")
        inspection = command(["docker", "buildx", "inspect", builder], "builder inspection")
        drivers = [line.partition(":")[2].strip()
                   for line in inspection.decode("utf-8").splitlines()
                   if line.partition(":")[0].strip() == "Driver"]
        if drivers != ["docker"]:
            raise TestFailure("the active context's builder must use the docker driver")
        for target, image in zip(targets, images):
            # Use this context's engine builder so the inspected local base remains
            # available; docker-container builders cannot see the loaded image store.
            command(["docker", "buildx", "build", "--builder", builder, "--load", "--pull=false",
                     "--network", "none", *platform,
                     "--file", str(root / "tests" / "Dockerfile"), "--build-arg", f"BASE_IMAGE={args.image}",
                     "--target", target, "--tag", image, str(root / "tests")],
                    f"build {target}", stream=True)
            print(f"PASS {target}: test image built", flush=True)
        for target, image in zip(targets, images):
            for mode in ("environment", "console-ascii", "console-unicode"):
                probe(image, mode)
                print(f"PASS {target}: {mode}", flush=True)
            probe(image, "environment", negative=True)
            print(f"PASS {target}: C-locale negative control", flush=True)
        print("PASS: 6 UTF-8 cases and 2 C-locale controls")
        return 0
    except TestFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (OSError, subprocess.TimeoutExpired):
        print("FAIL: Docker or PTY operation failed", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("FAIL: interrupted", file=sys.stderr)
        return 130
    finally:
        for name in containers:
            stop_own_container(name)
        try:
            subprocess.run(["docker", "image", "rm", *images], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            print("Cleanup: could not remove temporary test images", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
