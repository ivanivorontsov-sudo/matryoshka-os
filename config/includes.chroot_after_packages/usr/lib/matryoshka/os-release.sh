#!/bin/sh
set -e
BASE=/usr/lib/os-release
[ -f "$BASE" ] || exit 0
V=$(tr -d ' \n' < /etc/matryoshka-version 2>/dev/null || true)
[ -n "$V" ] || V=$(tr -d ' \n' < /usr/share/matryoshka/VERSION 2>/dev/null || true)
case "$V" in ""|*[!0-9.]*) V="";; esac
D=$(. "$BASE"; echo "${VERSION_ID:-13}")
C=$(. "$BASE"; echo "${VERSION_CODENAME:-trixie}")
U=https://github.com/ivanivorontsov-sudo/matryoshka-os
T=$(mktemp /etc/.os-release.XXXXXX)
{
  grep -vE '^(PRETTY_NAME|HOME_URL|SUPPORT_URL|BUG_REPORT_URL|VARIANT|VARIANT_ID|LOGO|IMAGE_ID|IMAGE_VERSION)=' "$BASE"
  echo "PRETTY_NAME=\"Матрёшка${V:+ $V} (на базе Debian $D)\""
  echo "VARIANT=\"Матрёшка${V:+ $V}\""
  echo "VARIANT_ID=matryoshka"
  [ -n "$V" ] && echo "IMAGE_ID=matryoshka" && echo "IMAGE_VERSION=$V"
  echo "LOGO=matryoshka"
  echo "HOME_URL=\"$U\""
  echo "SUPPORT_URL=\"$U\""
  echo "BUG_REPORT_URL=\"$U/issues\""
} > "$T"
chmod 644 "$T"
if [ -f /etc/os-release ] && [ ! -L /etc/os-release ] && cmp -s "$T" /etc/os-release; then rm -f "$T"; else mv -f "$T" /etc/os-release; fi
K=/etc/xdg/kcm-about-distrorc
mkdir -p /etc/xdg
T=$(mktemp /etc/xdg/.kcm-about-distrorc.XXXXXX)
printf '[General]\nName=Матрёшка\nLogoPath=/usr/share/matryoshka/logo-about.png\nWebsite=%s\nVariant=на базе Debian %s «%s»\nUseOSReleaseVersion=false\nVersion=%s\n' "$U" "$D" "$C" "${V:-$D}" > "$T"
chmod 644 "$T"
if cmp -s "$T" "$K"; then rm -f "$T"; else mv -f "$T" "$K"; fi
exit 0
