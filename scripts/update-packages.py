#!/usr/bin/env python3
"""Refresh PKGBUILDs from a published Veasel release and verify its manifest."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/veasel-labs/veasel/releases"
GIT_API = "https://api.github.com/repos/veasel-labs/veasel/git"
RAW = "https://raw.githubusercontent.com/veasel-labs/veasel"
USER_AGENT = "veasel-aur-package-updater"
TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-next\.\d+)?)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def request(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def resolve_release(tag: str | None) -> dict[str, object]:
    if tag:
        if not TAG_PATTERN.fullmatch(tag):
            raise ValueError(f"Unsupported Veasel tag: {tag}")
        release = json.loads(request(f"{API}/tags/{quote(tag, safe='')}"))
    else:
        releases = json.loads(request(f"{API}?per_page=100"))
        release = next((item for item in releases if not item["draft"]), None)
        if release is None:
            raise ValueError("No published Veasel release is available")
    if release["draft"]:
        raise ValueError("Draft releases cannot be packaged")
    if release.get("immutable") is not True:
        raise ValueError("Release is not immutable; refusing to publish package metadata")
    if not TAG_PATTERN.fullmatch(release["tag_name"]):
        raise ValueError(f"Unsupported Veasel tag: {release['tag_name']}")
    return release


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_tag_commit(tag: str) -> str:
    """Resolve a release tag, including annotated tags, to its commit SHA."""
    ref = json.loads(request(f"{GIT_API}/ref/tags/{quote(tag, safe='')}"))
    target = ref.get("object", {})
    for _ in range(5):
        target_type = target.get("type")
        target_sha = target.get("sha")
        if not isinstance(target_sha, str) or not GIT_SHA_PATTERN.fullmatch(target_sha):
            raise ValueError("Release tag points to an invalid Git object")
        if target_type == "commit":
            return target_sha
        if target_type != "tag":
            raise ValueError("Release tag does not resolve to a commit")
        annotated = json.loads(request(f"{GIT_API}/tags/{target_sha}"))
        target = annotated.get("object", {})
    raise ValueError("Release tag has too many nested annotated tags")


def verify_github_asset_digest(
    release: dict[str, object], name: str, data: bytes
) -> str:
    """Require GitHub's release API digest and verify the downloaded bytes."""
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("GitHub release metadata has no asset list")
    matching_assets = [
        item for item in assets if isinstance(item, dict) and item.get("name") == name
    ]
    if len(matching_assets) != 1:
        raise ValueError(f"GitHub release metadata has an ambiguous or missing {name} asset")
    asset = matching_assets[0]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ValueError(f"GitHub release metadata has no SHA-256 digest for {name}")
    expected = digest.removeprefix("sha256:")
    if not SHA256_PATTERN.fullmatch(expected):
        raise ValueError(f"GitHub release metadata has an invalid SHA-256 digest for {name}")
    actual = sha256(data)
    if actual != expected:
        raise ValueError(f"{name} digest does not match GitHub release metadata")
    return actual


def validate_linux_manifest(
    manifest: dict[str, object], tag_name: str, version: str, source_commit: str
) -> dict[str, object]:
    if manifest.get("tag") != tag_name or manifest.get("version") != version:
        raise ValueError("Release manifest tag/version do not match GitHub metadata")
    if manifest.get("source_commit") != source_commit:
        raise ValueError("Release manifest source commit does not match the release tag")
    platforms = manifest.get("platforms")
    linux = platforms.get("linux") if isinstance(platforms, dict) else None
    if (
        not isinstance(linux, dict)
        or linux.get("status") != "published"
        or linux.get("ci_result") != "success"
        or linux.get("arch") != "x86_64"
    ):
        raise ValueError("Release manifest does not declare a successful x86_64 Linux artifact")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Release manifest has no asset list")
    asset = next(
        (item for item in assets if isinstance(item, dict) and item.get("name") == "veasel-Linux.tar.gz"),
        None,
    )
    if not isinstance(asset, dict):
        raise ValueError("Release manifest has no Linux package archive")
    if (
        asset.get("platform") != "linux"
        or asset.get("arch") != "x86_64"
        or asset.get("kind") != "cli-archive"
    ):
        raise ValueError("Release manifest Linux archive metadata is inconsistent")
    digest = asset.get("sha256")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("Release manifest Linux archive has an invalid SHA-256 digest")
    return asset


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
    source_commit = resolve_tag_commit(tag_name)
    base = f"https://github.com/veasel-labs/veasel/releases/download/{tag_name}"
    manifest_bytes = request(f"{base}/release.json")
    verify_github_asset_digest(release, "release.json", manifest_bytes)
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("Release manifest must be a JSON object")
    asset = validate_linux_manifest(manifest, tag_name, version, source_commit)
    linux_archive = request(f"{base}/veasel-Linux.tar.gz")
    github_digest = verify_github_asset_digest(release, "veasel-Linux.tar.gz", linux_archive)
    if github_digest != asset["sha256"]:
        raise ValueError("Linux archive digest does not match release.json")
    validate_linux_bundle(linux_archive)
    license_file = request(f"{RAW}/{source_commit}/LICENSE")
    binary = ROOT / "create-veasel-code-bin/PKGBUILD"
    replace_pkg_metadata(binary, package_version, [sha256(linux_archive), sha256(license_file)])
    return tag_name


if __name__ == "__main__":
    try:
        print(f"Updated package metadata for {update(sys.argv[1] if len(sys.argv) > 1 else None)}")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"update-packages: {error}", file=sys.stderr)
        raise SystemExit(1) from error
