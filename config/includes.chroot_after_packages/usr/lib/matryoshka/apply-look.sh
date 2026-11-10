#!/bin/sh
set -e
if [ "$(id -u)" != 0 ]; then exec pkexec "$0" "$@"; fi
src=/usr/share/matryoshka/lockscreen/LockScreenUi.qml
dst=/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml
if [ -f "$src" ] && [ -d "$(dirname "$dst")" ]; then
  cp -a "$src" "$dst"
fi
f=/usr/share/applications/firefox-esr.desktop
if [ -f "$f" ]; then
  grep -q '^StartupWMClass=' "$f" || printf '\nStartupWMClass=firefox-esr\n' >> "$f"
  cat > /usr/share/applications/firefox.desktop <<'E'
[Desktop Entry]
Type=Application
NoDisplay=true
Name=Firefox
Exec=firefox-esr %u
Icon=firefox-esr
StartupWMClass=firefox
E
fi
[ -f /usr/lib/matryoshka/waydroid_desktop.py ] && python3 /usr/lib/matryoshka/waydroid_desktop.py --patch >/dev/null 2>&1 || true
t=/usr/share/sddm/themes/breeze/theme.conf
if [ -f "$t" ]; then
  if grep -q '^background=' "$t"; then
    sed -i 's#^background=.*#background=/usr/share/wallpapers/matryoshka/aurora.png#' "$t"
  else
    printf '\nbackground=/usr/share/wallpapers/matryoshka/aurora.png\ntype=image\n' >> "$t"
  fi
fi
mkdir -p /etc
[ -s /usr/share/matryoshka/VERSION ] && [ ! -s /etc/matryoshka-version ] && cp /usr/share/matryoshka/VERSION /etc/matryoshka-version
[ -x /usr/lib/matryoshka/os-release.sh ] && /usr/lib/matryoshka/os-release.sh || true
if [ -x /usr/bin/gtk-update-icon-cache ] && { [ /usr/share/icons/hicolor/scalable/apps/matryoshka-center.svg -nt /usr/share/icons/hicolor/icon-theme.cache ] || [ /usr/share/icons/hicolor/256x256/apps/matryoshka.png -nt /usr/share/icons/hicolor/icon-theme.cache ]; }; then gtk-update-icon-cache -q -f /usr/share/icons/hicolor >/dev/null 2>&1 || true; fi
exit 0
