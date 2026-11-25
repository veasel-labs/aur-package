#!/usr/bin/env bash
set -euo pipefail

pacman -Syu --noconfirm --needed namcap shadow
pacman -S --noconfirm --needed at-spi2-core gtk3 libnotify libsecret libxss libxtst nss util-linux-libs xdg-utils
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
	local package_name="$2"
	local expected_pkgver expected_pkgrel expected_app_version expected_package_version
	expected_pkgver="$(sed -n 's/^pkgver=//p' "$package_dir/PKGBUILD")"
	expected_pkgrel="$(sed -n 's/^pkgrel=//p' "$package_dir/PKGBUILD")"
	expected_app_version="$(application_version "$package_dir/PKGBUILD")"
	expected_package_version="${expected_pkgver}-${expected_pkgrel}"
	pacman -U --noconfirm "$package_dir"/"${package_name}"-*.pkg.tar.zst
	[[ "$(pacman -Q "$package_name" | awk '{print $2}')" == "$expected_package_version" ]]
	if [[ "$package_name" == veasel-code-bin ]]; then
		[[ "$(veasel --version)" == "Veasel Code ${expected_app_version}" ]]
		test -x /usr/lib/veasel-code/veasel-tui
		[[ "$(/usr/lib/veasel-code/veasel-tui --version)" == "Veasel Code Terminal ${expected_app_version}" ]]
		test -f /usr/share/veasel-code/build.json
		if pacman -Ql veasel-code-bin | grep -F ' /usr/share/applications/veasel-tui.desktop' >/dev/null; then
			test -f /usr/share/applications/veasel-tui.desktop
			grep -Fxq 'Exec=veasel' /usr/share/applications/veasel-tui.desktop
			grep -Fxq 'Terminal=true' /usr/share/applications/veasel-tui.desktop
		else
			test ! -e /usr/share/applications/veasel-tui.desktop
		fi
	else
		test -x /opt/Veasel/veasel-desktop
		[[ "$(/opt/Veasel/resources/bin/veasel --version)" == "Veasel Code ${expected_app_version}" ]]
		grep -Fxq 'Exec=/opt/Veasel/veasel-desktop %U' /usr/share/applications/veasel-desktop.desktop
		grep -Fxq 'Terminal=false' /usr/share/applications/veasel-desktop.desktop
		test -f /usr/share/icons/hicolor/512x512/apps/veasel-desktop.png
	fi
}

build_package /workspace/create-veasel-code-bin /tmp/current-veasel-code-bin
build_package /workspace/veasel-desktop-bin /tmp/current-veasel-desktop-bin

if [[ "${HAS_PREVIOUS_CLI:-false}" == "true" ]]; then
	build_package /previous/create-veasel-code-bin /tmp/previous-veasel-code-bin
	previous_version="$(package_version /tmp/previous-veasel-code-bin/PKGBUILD)"
	current_version="$(package_version /tmp/current-veasel-code-bin/PKGBUILD)"
	if (( $(vercmp "$current_version" "$previous_version") <= 0 )); then
		echo "Current CLI package $current_version is not newer than base package $previous_version." >&2
		exit 1
	fi
	install_package /tmp/previous-veasel-code-bin veasel-code-bin
fi

if [[ "${HAS_PREVIOUS_DESKTOP:-false}" == "true" ]]; then
	build_package /previous/veasel-desktop-bin /tmp/previous-veasel-desktop-bin
	previous_version="$(package_version /tmp/previous-veasel-desktop-bin/PKGBUILD)"
	current_version="$(package_version /tmp/current-veasel-desktop-bin/PKGBUILD)"
	if (( $(vercmp "$current_version" "$previous_version") <= 0 )); then
		echo "Current Desktop package $current_version is not newer than base package $previous_version." >&2
		exit 1
	fi
	install_package /tmp/previous-veasel-desktop-bin veasel-desktop-bin
fi

install_package /tmp/current-veasel-code-bin veasel-code-bin
install_package /tmp/current-veasel-desktop-bin veasel-desktop-bin
pacman -Rns --noconfirm veasel-code-bin veasel-desktop-bin
test ! -e /usr/bin/veasel
test ! -e /usr/lib/veasel-code/veasel-tui
test ! -e /usr/share/veasel-code/build.json
test ! -e /usr/share/applications/veasel-tui.desktop
test ! -e /opt/Veasel/veasel-desktop
test ! -e /usr/share/applications/veasel-desktop.desktop
test ! -e /usr/share/icons/hicolor/512x512/apps/veasel-desktop.png

echo "AUR CLI/TUI and Desktop package install and uninstall acceptance passed."
