#!/usr/bin/env python3
"""Guard AUR publication against stale, unreviewed, or already-published data."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RPC = "https://aur.archlinux.org/rpc/v5/info/veasel-code-bin"
TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-next\.\d+)?)$")
PKGVER = re.compile(r"(?m)^pkgver=(\S+)$")


def version_key(version: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.next\.(\d+))?", version)
    if not match:
        raise ValueError(f"Unsupported package version: {version}")
    major, minor, patch, prerelease = match.groups()
    # Stable releases sort after prereleases of the same base version.
    return int(major), int(minor), int(patch), 1 if prerelease is None else 0, int(prerelease or 0)


def rpc_version() -> str:
    request = urllib.request.Request(RPC, headers={"User-Agent": "veasel-aur-publisher"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    results = payload.get("results", [])
    if len(results) != 1 or results[0].get("Name") != "veasel-code-bin":
        raise ValueError("AUR RPC did not return exactly one veasel-code-bin package")
    return str(results[0]["Version"])


def expected_package_version(tag: str) -> str:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Unsupported Veasel release tag: {tag}")
    return match.group("version").replace("-next.", ".next.")


def package_version(pkgbuild: Path) -> str:
    match = PKGVER.search(pkgbuild.read_text())
    if match is None:
        raise ValueError(f"Missing pkgver in {pkgbuild}")
    return match.group(1)


def check(tag: str, pkgbuild: Path, remote_pkgbuild: Path | None = None) -> str:
    expected = expected_package_version(tag)
    actual = package_version(pkgbuild)
    if actual != expected:
        raise ValueError(f"Reviewed PKGBUILD pkgver {actual} does not match requested {expected}")
    observed = [rpc_version().rsplit("-", 1)[0]]
    if remote_pkgbuild is not None:
        observed.append(package_version(remote_pkgbuild))
    current = max(observed, key=version_key)
    if version_key(current) > version_key(expected):
        raise ValueError(f"AUR already has newer version {current}; refusing downgrade to {expected}")
    return "already-current" if version_key(current) == version_key(expected) else "publish"


def wait(tag: str, timeout: int = 900) -> None:
    expected = expected_package_version(tag)
    deadline = time.monotonic() + timeout
    while True:
        current = rpc_version()
        current_ver = current.rsplit("-", 1)[0]
        if version_key(current_ver) == version_key(expected):
            return
        if version_key(current_ver) > version_key(expected):
            raise ValueError(f"AUR reports newer unexpected version {current}, expected {expected}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"AUR RPC did not report {expected} within {timeout} seconds")
        time.sleep(15)


if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        tag = sys.argv[2]
        if mode == "check":
            path = Path(sys.argv[3])
            print(check(tag, path, Path(sys.argv[4]) if len(sys.argv) > 4 else None))
        elif mode == "wait":
            wait(tag)
            print(f"AUR RPC confirms {expected_package_version(tag)}")
        else:
            raise ValueError(f"Unknown mode: {mode}")
    except (OSError, ValueError, KeyError, TimeoutError, IndexError) as error:
        print(f"aur_publish_gate: {error}", file=sys.stderr)
        raise SystemExit(1) from error
