#!/usr/bin/env bash
set -euo pipefail

pacman -Syu --noconfirm --needed namcap shadow
useradd --create-home builder

build_package() {
	local source_dir="$1"
	local build_dir="$2"
	cp -a "$source_dir" "$build_dir"
	chown -R builder:builder "$build_dir"
	su builder -c "cd '$build_dir' && bash -n PKGBUILD && makepkg --printsrcinfo > /tmp/SRCINFO && diff -u .SRCINFO /tmp/SRCINFO && namcap PKGBUILD && makepkg --cleanbuild --noconfirm"
}

package_version() {
	local pkgbuild="$1"
	local pkgver pkgrel
	pkgver="$(sed -n 's/^pkgver=//p' "$pkgbuild")"
	pkgrel="$(sed -n 's/^pkgrel=//p' "$pkgbuild")"
	printf '%s-%s\n' "$pkgver" "$pkgrel"
}

application_version() {
	sed -n 's/^pkgver=//p' "$1" | sed 's/\.next\./-next./'
}

install_package() {
	local package_dir="$1"
	local expected_pkgver expected_pkgrel expected_app_version expected_package_version
	expected_pkgver="$(sed -n 's/^pkgver=//p' "$package_dir/PKGBUILD")"
	expected_pkgrel="$(sed -n 's/^pkgrel=//p' "$package_dir/PKGBUILD")"
	expected_app_version="$(application_version "$package_dir/PKGBUILD")"
	expected_package_version="${expected_pkgver}-${expected_pkgrel}"
	pacman -U --noconfirm "$package_dir"/veasel-code-bin-*.pkg.tar.zst
	[[ "$(pacman -Q veasel-code-bin | awk '{print $2}')" == "$expected_package_version" ]]
	[[ "$(veasel --version)" == "Veasel Code ${expected_app_version}" ]]
	test -x /usr/lib/veasel-code/veasel-tui
	[[ "$(/usr/lib/veasel-code/veasel-tui --version)" == "Veasel Code Terminal ${expected_app_version}" ]]
	test -f /usr/share/veasel-code/build.json
}

build_package /workspace/create-veasel-code-bin /tmp/current-package

if [[ "${HAS_PREVIOUS_PACKAGE:-false}" == "true" ]]; then
	build_package /previous /tmp/previous-package
	previous_version="$(package_version /tmp/previous-package/PKGBUILD)"
	current_version="$(package_version /tmp/current-package/PKGBUILD)"
	if (( $(vercmp "$current_version" "$previous_version") <= 0 )); then
		echo "Current package $current_version is not newer than base package $previous_version." >&2
		exit 1
	fi
	install_package /tmp/previous-package
fi

install_package /tmp/current-package
pacman -Rns --noconfirm veasel-code-bin
test ! -e /usr/bin/veasel
test ! -e /usr/lib/veasel-code/veasel
test ! -e /usr/lib/veasel-code/veasel-tui
test ! -e /usr/share/veasel-code/build.json

if [[ "${HAS_PREVIOUS_PACKAGE:-false}" == "true" ]]; then
	echo "AUR package install, upgrade, and uninstall acceptance passed."
else
	echo "AUR package clean install and uninstall acceptance passed."
fi
