#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE=""
if [ -r "$SCRIPT_DIR/VERSION.txt" ]; then
  IFS= read -r RELEASE < "$SCRIPT_DIR/VERSION.txt" || true
fi
printf '%s — Termux kurulumu\n' "${RELEASE:-APK Cleaner Studio}"
pkg update -y
pkg install -y python python-cryptography
if pkg show openjdk-25 >/dev/null 2>&1; then
  pkg install -y openjdk-25
else
  echo "OpenJDK 25 bu Termux deposunda bulunamadı; uyumlu OpenJDK 21 kuruluyor."
  pkg install -y openjdk-21
fi
termux-setup-storage || true

cd "$SCRIPT_DIR"
python studio/setup_tools.py

mkdir -p "$HOME/.shortcuts"
LAUNCHER="$HOME/.shortcuts/APK Cleaner Studio"
printf '#!/data/data/com.termux/files/usr/bin/bash\nbash %q/start-termux.sh\n' "$SCRIPT_DIR" > "$LAUNCHER"
chmod +x "$LAUNCHER" "$SCRIPT_DIR/start-termux.sh"

echo
echo "Kurulum tamamlandi."
echo "Gunluk kullanim icin start-termux.sh dosyasini calistir."
echo "Termux:Widget varsa 'APK Cleaner Studio' kısayoluna dokunabilirsin."
