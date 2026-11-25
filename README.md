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
| [`veasel-code-bin`](https://aur.archlinux.org/packages/veasel-code-bin) | Terminal CLI/TUI only; does not install Veasel Desktop. | `yay -S veasel-code-bin` |
| `veasel-desktop-bin` (GitHub mirror; AUR registration pending) | Optional Desktop app with Focus and World, from the official verified Linux `.deb`. | After AUR registration: `yay -S veasel-desktop-bin` |

`veasel-code-bin` installs the native `veasel` backend and its standalone terminal client; it does **not** include the graphical Desktop app. `veasel-desktop-bin` is packaged separately from the official Linux Desktop installer and bundles its own V backend. It declares Arch runtime dependencies and adds a desktop launcher; it does not conflict with the CLI/TUI package. The GitHub mirror is ready for review, but the new Desktop package is not yet registered in AUR, so the `yay` command becomes available only after its first reviewed AUR publication. Bun and V are not runtime dependencies.
Run `veasel` to start or reuse the local backend and open the TUI. Use
`/connect` on the home screen to configure a provider and model, then press
`n` to create a project session before sending prompts. Press `s` for advanced
provider/model settings such as endpoint overrides. Run `veasel serve` to
start only the server. Linux release archives that include `veasel-tui.desktop`
also register the CLI in desktop launchers; the entry runs in a terminal as
the invoking user, with no autostart or privileged helper.

## Automated updates

The scheduled candidate workflow follows Veasel's public prereleases, matches
the CLI archive and Desktop `.deb` against GitHub's release digests and manifest,
and verifies the manifest source commit against the immutable release tag. It
refreshes both PKGBUILDs, builds and install-tests both packages in Arch Linux,
then opens a draft PR for this GitHub mirror. After the exact metadata is
reviewed and merged, a maintainer can manually run the separate approved
publisher on the reviewed `main` revision. The publisher checks AUR RPC state
before and after publishing and refuses downgrades or duplicate updates.

Maintainer credentials are stored only as the `AUR_SSH_PRIVATE_KEY` Actions
secret; pull-request workflows and the scheduled candidate workflow never
receive that secret.

## Release sync

The scheduled **Propose AUR mirror candidate** workflow follows the newest
public Veasel release, verifies its manifest and Linux archive, builds the
package in Arch Linux, and proposes matching files for this GitHub mirror in a
draft PR. The separate **Publish approved package to AUR** workflow publishes
only the version recorded in reviewed `main` metadata. The exact package version is recorded in
[`create-veasel-code-bin/PKGBUILD`](create-veasel-code-bin/PKGBUILD), so this
README does not drift behind automated updates.

## Local validation

On Arch Linux:

```sh
for package in create-veasel-code-bin veasel-desktop-bin; do
  (cd "$package" && makepkg --printsrcinfo > .SRCINFO && makepkg --syncdeps --cleanbuild && namcap PKGBUILD ./*.pkg.tar.zst)
done
```

Run `python -m unittest discover -s scripts -p 'test_*.py'` for the release
metadata updater tests. The release workflow tracks public prereleases; verify
the corresponding tagged GitHub release before reporting a package version.
The Desktop mirror is under `veasel-desktop-bin/`; run the same commands there.

## License

The packaging metadata and updater are MIT licensed. Veasel's own source and
mascot artwork retain the notices distributed with the selected release.
