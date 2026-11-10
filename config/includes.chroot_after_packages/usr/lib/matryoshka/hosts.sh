#!/bin/sh
F=/etc/hosts
h=$(hostname 2>/dev/null)
if [ -n "$h" ] && [ "$h" != localhost ] && ! awk -v h="$h" '$1 !~ /^#/ { for (i = 2; i <= NF; i++) if ($i == h) f = 1 } END { exit !f }' "$F" 2>/dev/null; then
  if grep -q '^127\.0\.1\.1[[:space:]]' "$F" 2>/dev/null; then
    sed -i "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$h/" "$F"
  else
    { printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n' "$h"; grep -v '^127\.0\.0\.1[[:space:]]\+localhost[[:space:]]*$' "$F" 2>/dev/null; } > "$F.matryoshka-new" && cat "$F.matryoshka-new" > "$F" && rm -f "$F.matryoshka-new"
  fi
fi
grep -q StevenBlack "$F" || { echo '# StevenBlack unified hosts'; grep -E '^0\.0\.0\.0 ' /usr/share/matryoshka/hosts/stevenblack | grep -v ' 0\.0\.0\.0$'; } >> "$F"
exit 0
