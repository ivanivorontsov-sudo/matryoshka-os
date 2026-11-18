#!/bin/sh
# Собирает matryoshka-office и кладёт .deb туда, откуда live-build ставит его в ISO.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
VER=$(sed -n 's/__version__ = "\(.*\)"/\1/p' "$HERE/matryoshka_office/__init__.py")
OUT=${1:-$HERE/../../config/packages.chroot}
R=$(mktemp -d)
chmod 755 "$R"
trap 'rm -rf "$R"' EXIT
install -d \
  "$R/DEBIAN" \
  "$R/usr/bin" \
  "$R/usr/lib/matryoshka-office/matryoshka_office" \
  "$R/usr/share/applications" \
  "$R/usr/share/icons/hicolor/scalable/apps" \
  "$R/usr/share/doc/matryoshka-office"
install -m644 "$HERE"/matryoshka_office/*.py "$R/usr/lib/matryoshka-office/matryoshka_office/"
install -m644 "$HERE/THIRD-PARTY.md" "$R/usr/share/doc/matryoshka-office/THIRD-PARTY.md"
install -m644 "$HERE"/share/*.svg "$R/usr/share/icons/hicolor/scalable/apps/"
python3 -m pip install --target "$R/usr/lib/matryoshka-office/vendor" --upgrade --no-deps \
  'formulas==1.3.4' 'schedula==1.6.15' 'numpy-financial==1.0.0' \
  'python-pptx==1.0.2' 'XlsxWriter==3.3.1' \
  'oletools==0.60.2' 'pyparsing==3.3.3' 'pcodedmp==1.2.6' 'colorclass==2.2.2' 'msoffcrypto-tool==6.1.0'
rm -rf "$R/usr/lib/matryoshka-office/vendor/bin"
find "$R/usr/lib/matryoshka-office" -type d -name __pycache__ -exec rm -rf {} +
find "$R/usr/lib/matryoshka-office" -type d -name tests -prune -exec rm -rf {} +
cat > "$R/usr/bin/matryoshka-office" <<'SH'
#!/bin/sh
export PYTHONPATH="/usr/lib/matryoshka-office:/usr/lib/matryoshka-office/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m matryoshka_office "$@"
SH
chmod 755 "$R/usr/bin/matryoshka-office"
for name in matryoshka-pismo matryoshka-tablitsy matryoshka-prezentacii; do
  ln -s matryoshka-office "$R/usr/bin/$name"
done
python3 - "$R/usr/share/applications" <<'PY'
import os, sys
out = sys.argv[1]
apps = [
    ("matryoshka-pismo", "Письмо", "Документы: стили, таблицы, разделы, ссылки",
     "Office;WordProcessor;",
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document;application/msword;application/vnd.oasis.opendocument.text;application/rtf;"),
    ("matryoshka-tablitsy", "Таблицы", "Листы, формулы Excel, диаграммы, сводные",
     "Office;Spreadsheet;",
     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;application/vnd.ms-excel;application/vnd.oasis.opendocument.spreadsheet;text/csv;"),
    ("matryoshka-prezentacii", "Презентации", "Слайды, темы, переходы, режим докладчика",
     "Office;Presentation;",
     "application/vnd.openxmlformats-officedocument.presentationml.presentation;application/vnd.ms-powerpoint;application/vnd.oasis.opendocument.presentation;"),
    ("matryoshka-office", "Матрёшка Офис", "Письмо, Таблицы и Презентации",
     "Office;", ""),
]
for name, title, comment, cats, mime in apps:
    text = "[Desktop Entry]\nType=Application\nName=%s\nComment=%s\nExec=%s %%U\nIcon=%s\nCategories=%s\nStartupWMClass=%s\n" % (title, comment, name, name, cats, name)
    if mime:
        text += "MimeType=%s\n" % mime
    open(os.path.join(out, name + ".desktop"), "w", encoding="utf-8").write(text)
PY
cat > "$R/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  update-desktop-database -q /usr/share/applications || true
fi
SH
chmod 755 "$R/DEBIAN/postinst"
cat > "$R/usr/share/doc/matryoshka-office/copyright" <<'TXT'
Matryoshka Office (Pismo, Tablitsy, Prezentacii).
Copyright (c) 2026 Ivan Vorontsov. License: GPL-3.0-only.
Third-party libraries keep their own licenses: see THIRD-PARTY.md.
TXT
cat > "$R/DEBIAN/control" <<CTL
Package: matryoshka-office
Version: $VER
Architecture: all
Maintainer: Ivan Vorontsov <ivanivorontsov-sudo@users.noreply.github.com>
Depends: python3, python3-pyqt6, python3-pyqt6.qtcharts, python3-lxml, python3-docx, python3-openpyxl, python3-olefile, python3-odf, python3-pil, python3-reportlab, python3-xlrd, python3-xlwt, python3-numpy, python3-scipy, python3-dateutil, python3-regex, python3-tqdm, python3-cryptography
Section: editors
Priority: optional
Description: Matryoshka office: documents, spreadsheets, slides
 Pismo, Tablitsy and Prezentacii edit OOXML directly.
 LibreOffice is not used. VBA projects are kept byte-for-byte.
CTL
mkdir -p "$OUT"
dpkg-deb --root-owner-group -Zxz -b "$R" "$OUT/matryoshka-office_${VER}_all.deb" >/dev/null
echo "$OUT/matryoshka-office_${VER}_all.deb"
