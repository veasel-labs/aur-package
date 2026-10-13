#!/usr/bin/env python3
"""Refresh PKGBUILDs from a published Veasel release and verify its manifest."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/veasel-labs/veasel/releases"
USER_AGENT = "veasel-aur-package-updater"
TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-next\.\d+)?)$")


def request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def resolve_release(tag: str | None) -> dict[str, object]:
    releases = json.loads(request(f"{API}?per_page=100"))
    if tag:
        release = next((item for item in releases if item["tag_name"] == tag), None)
    else:
        release = next((item for item in releases if not item["draft"]), None)
    if release is None:
        raise ValueError(f"Veasel release not found: {tag or 'latest'}")
    if release["draft"]:
        raise ValueError("Draft releases cannot be packaged")
    if not TAG_PATTERN.fullmatch(release["tag_name"]):
        raise ValueError(f"Unsupported Veasel tag: {release['tag_name']}")
    return release


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_linux_bundle(archive_data: bytes) -> None:
    required_files = {"veasel", "veasel-tui", "build.json"}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            members = {member.name: member for member in archive.getmembers()}
    except tarfile.TarError as error:
        raise ValueError("Linux release asset is not a valid gzip tar archive") from error

    missing = sorted(required_files - members.keys())
    if missing:
        raise ValueError(f"Linux release archive is missing required files: {', '.join(missing)}")
    for name in required_files:
        if not members[name].isfile():
            raise ValueError(f"Linux release archive entry is not a regular file: {name}")


def replace_pkg_metadata(path: Path, version: str, hashes: list[str]) -> None:
    content = path.read_text()
    content, changed = re.subn(r"(?m)^pkgver=.*$", f"pkgver={version}", content, count=1)
    if changed != 1:
        raise ValueError(f"pkgver is missing from {path}")
    checksum_block = "sha256sums=(\n" + "\n".join(f"  '{digest}'" for digest in hashes) + "\n)"
    pattern = r"(?ms)^sha256sums=\(.*?^\)"
    content, changed = re.subn(pattern, lambda _match: checksum_block, content, count=1)
    if changed != 1:
        raise ValueError(f"sha256sums is missing from {path}")
    path.write_text(content)


def update(tag: str | None) -> str:
    release = resolve_release(tag)
    tag_name = str(release["tag_name"])
    matched_tag = TAG_PATTERN.fullmatch(tag_name)
    if matched_tag is None:
        raise ValueError(f"Unsupported Veasel tag: {tag_name}")
    version = matched_tag.group("version")
    package_version = version.replace("-next.", ".next.")
    manifest_url = f"https://github.com/veasel-labs/veasel/releases/download/{tag_name}/release.json"
    manifest = json.loads(request(manifest_url))
    if manifest.get("tag") != tag_name or manifest.get("version") != version:
        raise ValueError("Release manifest tag/version do not match GitHub metadata")
    asset = next((item for item in manifest["assets"] if item["name"] == "veasel-Linux.tar.gz"), None)
    if asset is None:
        raise ValueError("Release manifest has no Linux package archive")
    base = f"https://github.com/veasel-labs/veasel/releases/download/{tag_name}"
    linux_archive = request(f"{base}/veasel-Linux.tar.gz")
    if sha256(linux_archive) != asset["sha256"]:
        raise ValueError("Linux archive digest does not match release.json")
    validate_linux_bundle(linux_archive)
    license_file = request(f"https://raw.githubusercontent.com/veasel-labs/veasel/{tag_name}/LICENSE")
    binary = ROOT / "create-veasel-code-bin/PKGBUILD"
    replace_pkg_metadata(binary, package_version, [sha256(linux_archive), sha256(license_file)])
    return tag_name


if __name__ == "__main__":
    try:
        print(f"Updated package metadata for {update(sys.argv[1] if len(sys.argv) > 1 else None)}")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"update-packages: {error}", file=sys.stderr)
        raise SystemExit(1) from error
