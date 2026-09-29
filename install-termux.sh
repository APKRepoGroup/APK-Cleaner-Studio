#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "APK Cleaner Studio v0.6.3-dev.2 Termux kurulumu"
pkg update -y
pkg install -y python python-cryptography
if pkg show openjdk-25 >/dev/null 2>&1; then
  pkg install -y openjdk-25
else
  echo "OpenJDK 25 bu Termux deposunda bulunamadı; uyumlu OpenJDK 21 kuruluyor."
  pkg install -y openjdk-21
fi
termux-setup-storage || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
