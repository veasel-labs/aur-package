# Veasel Code AUR packages

[![Package CI](https://github.com/veasel-labs/aur-package/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/veasel-labs/aur-package/actions/workflows/ci.yml)
[![AUR package](https://img.shields.io/aur/version/veasel-code-bin?label=AUR&logo=archlinux)](https://aur.archlinux.org/packages/veasel-code-bin)
[![Veasel Code](https://img.shields.io/github/v/release/veasel-labs/veasel?include_prereleases&label=Veasel%20Code)](https://github.com/veasel-labs/veasel/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-4b6b52.svg)](LICENSE)

The package installs the official x86_64 Linux backend and bundled terminal
client from the GitHub release, verifying SHA-256 checksums. It does not
require an AUR package for the V compiler. The GitHub repository mirrors the
exact files published to AUR.

## Choose a package

| AUR package | Build | Install |
|---|---|---|
| [`veasel-code-bin`](https://aur.archlinux.org/packages/veasel-code-bin) | Installs the official x86_64 Linux backend and bundled terminal client from the verified GitHub release. | `yay -S veasel-code-bin` |

The package installs the native `veasel` backend and its standalone terminal client; Bun is not required at runtime.
Run `veasel` to start or reuse the local backend and open the TUI. Press `s` to
configure the provider, model, endpoint, and API key. Run `veasel serve` to
start only the server.

## Automated updates

The scheduled publisher follows Veasel's public prereleases, validates the
release manifest checksum, refreshes the PKGBUILD, builds and inspects the
package in Arch Linux, then pushes it to AUR over SSH. The same PKGBUILD and
generated `.SRCINFO` are committed to this GitHub mirror.
Maintainer credentials are stored only as the `AUR_SSH_PRIVATE_KEY` Actions
secret; pull-request workflows never receive that secret.

## Current sync status

As of 2026-10-15 the PKGBUILD tracks **`v0.41.0-next.0`**
(`pkgver=0.41.0.next.0`), the newest verified public prerelease. This package
does **not** invent tags or digests: when a newer verified prerelease publishes,
re-run **Publish packages to AUR** (or wait for the schedule).

## Local validation

On Arch Linux:

```sh
cd create-veasel-code-bin
makepkg --printsrcinfo > .SRCINFO
makepkg --syncdeps --cleanbuild
namcap PKGBUILD ./*.pkg.tar.zst
```

Run `python -m unittest discover -s scripts -p 'test_*.py'` for the release
metadata updater tests. The release workflow tracks public prereleases; verify
the corresponding tagged GitHub release before reporting a package version.

## License

The packaging metadata and updater are MIT licensed. Veasel's own source and
mascot artwork retain the notices distributed with the selected release.
