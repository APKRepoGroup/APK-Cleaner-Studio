# Windows pencere prototipi — dev.6

Bu başlatıcı uygulamayı WebView2 tabanlı kendi Windows penceresinde açar. Dağıtım derlemesi değildir; mevcut EXE, konsol/tarayıcı başlatıcıları ve paketleme ayarları değiştirilmedi.

- Bu bilgisayarda hazırlanan `outputs/APK Cleaner Studio - Pencere Prototipi.lnk` kısayoluna çift tıklayın. CMD penceresi açılmaz.
- Normal arayüz ve gerçek yerel işlem motoru kullanılır. Prototip dosyaları ve geçmişi `.codex-temp-dev6/windows-prototype/data` altında ayrıdır; normal uygulama verilerine erişilmez.
- Yalnız `127.0.0.1:18082` üzerinden çalışır. LAN erişimi, sertifika kurulumu, otomatik güncelleme ve bileşen indirme kapalıdır. Eksik bileşen otomatik indirilmez.
- Sağ üstteki X pencereyi ve prototip motorunu kapatır. Analiz/işlem sürüyorsa önce onay istenir. Küçültme işlemi motoru durdurmaz.
- Haricî siteler ve yeni tarayıcı pencereleri prototipte engellenir. Yerel çıktı indirme için dosya kaydetme penceresi açıktır.
- Konsol yerine günlük dosyası kullanılır: `.codex-temp-dev6/windows-prototype/prototype.log` (2 MB, iki eski kopya).

## Geri dönüş

Prototipi X ile kapatıp mevcut Windows EXE'sini veya `APK-Cleaner-Studio.bat` başlatıcısını kullanın. Kalıcı geçiş yapılmadığı için kod geri alma veya yeniden derleme gerekmez.

## Kaynaktan çalıştırma

Windows, .NET Framework ve WebView2 Runtime gerektirir. Bağımlılıklar sistem Python'una değil `.codex-temp-dev6/desktop-deps` klasörüne kurulmuştur. `desktop_preview.py` bu klasörü kendisi ekler; `pythonw.exe` ile çalıştırıldığında konsol gösterilmez. Kısayol, yalnız bu bilgisayarda bulunan Python çalışma zamanına işaret eder.

Prototip bağımlılıklarını başka bir geliştirme ortamında kurmak için:

```powershell
python -m pip install --target .codex-temp-dev6/desktop-deps -r prototypes/windows/requirements.txt
pythonw prototypes/windows/desktop_preview.py
```

Bu prototip henüz yayımlanan pakete veya ana Windows dağıtımına eklenmedi.
