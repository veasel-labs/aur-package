#!/usr/bin/env python3
"""Guard AUR publication against stale, unreviewed, or already-published data."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RPC = "https://aur.archlinux.org/rpc/v5/info"
TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-next\.\d+)?)$")
PKGVER = re.compile(r"(?m)^pkgver=(\S+)$")


def version_key(version: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.next\.(\d+))?", version)
    if not match:
        raise ValueError(f"Unsupported package version: {version}")
    major, minor, patch, prerelease = match.groups()
    # Stable releases sort after prereleases of the same base version.
    return int(major), int(minor), int(patch), 1 if prerelease is None else 0, int(prerelease or 0)


def rpc_version(package_name: str = "veasel-code-bin") -> str | None:
    request = urllib.request.Request(
        f"{RPC}/{package_name}", headers={"User-Agent": "veasel-aur-publisher"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    results = payload.get("results", [])
    if not results:
        return None
    if len(results) != 1 or results[0].get("Name") != package_name:
        raise ValueError(f"AUR RPC did not return exactly one {package_name} package")
    return str(results[0]["Version"])


def registration_status(package_name: str) -> str:
    """Return the AUR registration state, propagating transport failures."""
    return "registered" if rpc_version(package_name) is not None else "unregistered"


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


def check(
    tag: str,
    pkgbuild: Path,
    remote_pkgbuild: Path | None = None,
    package_name: str = "veasel-code-bin",
) -> str:
    expected = expected_package_version(tag)
    actual = package_version(pkgbuild)
    if actual != expected:
        raise ValueError(f"Reviewed PKGBUILD pkgver {actual} does not match requested {expected}")
    remote = rpc_version(package_name)
    observed = [remote.rsplit("-", 1)[0]] if remote is not None else []
    if remote_pkgbuild is not None and remote_pkgbuild.is_file():
        observed.append(package_version(remote_pkgbuild))
    if not observed:
        return "publish"
    current = max(observed, key=version_key)
    if version_key(current) > version_key(expected):
        raise ValueError(f"AUR already has newer version {current}; refusing downgrade to {expected}")
    return "already-current" if version_key(current) == version_key(expected) else "publish"


def wait(tag: str, timeout: int = 900, package_name: str = "veasel-code-bin") -> None:
    expected = expected_package_version(tag)
    deadline = time.monotonic() + timeout
    while True:
        current = rpc_version(package_name)
        if current is None:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"AUR RPC did not report {expected} within {timeout} seconds")
            time.sleep(15)
            continue
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
            package_name = sys.argv[4] if len(sys.argv) > 4 else "veasel-code-bin"
            remote = Path(sys.argv[5]) if len(sys.argv) > 5 else None
            print(check(tag, path, remote, package_name))
        elif mode == "wait":
            package_name = sys.argv[3] if len(sys.argv) > 3 else "veasel-code-bin"
            wait(tag, package_name=package_name)
            print(f"AUR RPC confirms {package_name} {expected_package_version(tag)}")
        elif mode == "registration":
            package_name = sys.argv[2]
            print(registration_status(package_name))
        else:
            raise ValueError(f"Unknown mode: {mode}")
    except (OSError, ValueError, KeyError, TimeoutError, IndexError) as error:
        print(f"aur_publish_gate: {error}", file=sys.stderr)
        raise SystemExit(1) from error
