# Windows pencere prototipi — dev.6

Bu başlatıcı uygulamayı WebView2 tabanlı kendi Windows penceresinde açar. Dağıtım derlemesi değildir; mevcut EXE, konsol/tarayıcı başlatıcıları ve paketleme ayarları değiştirilmedi.

## Kullanıcı kararı — 2026-10-20

- Dev.6 Windows sürümü için mevcut arayüzü kendi penceresinde açan ilk prototip esas alınacak. İkinci prototipin masaüstü düzeni bu sürüme taşınmayacak.
- 2026-10-21: ilk prototipin pencere davranışı `studio/desktop.py` üzerinden dev.6 Windows dağıtımına entegre edildi ve yalnız Windows EXE'si üretildi. Normal sürümde güncelleme ve bileşen kurulumu açıktır; aşağıdaki indirme/güncelleme kısıtlamaları yalnız eski deneme başlatıcısına aittir.
- İkinci prototip ayrı olarak korunacak; geliştirmesi şimdilik ertelendi. 0.6.4 veya 0.6.5 döneminde yeniden değerlendirilebilir; belirli bir sürüm için yayın taahhüdü yoktur.
- İkinci düzen ileride yeterli çalışma ve kullanıcı testi sonrasında ele alınacak; mevcut uygulamanın üzerine yazılmayacak.

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

## İkinci deneme: masaüstüne özel düzen

`outputs/APK Cleaner Studio - Masaustu Duzen Prototipi.lnk` ayrı bir denemedir.
`desktop_workspace.py` ile açılır; `127.0.0.1:18083` kullanır. Solda bölüm menüsü,
ayrı geçmiş/depolama/motor ekranları ve doğrudan paket çalışma alanı sunar.
Sayfalar arasında geçiş seçili paketi veya süren işlemi sıfırlamaz.

Veriler, günlük ve WebView profili `.codex-temp-dev6/windows-workspace-prototype`
altında ayrıdır. İlk prototipin dosyaları ve verileri de değiştirilmez. Düzen
uyarlaması yalnız bu başlatıcının sunduğu yanıta eklenir; `studio/web` kaynakları
ve dağıtım başlatıcıları aynen korunur. Önceki denemeye dönmek için bu pencereyi
kapatıp ilk prototip kısayolunu açın.

Arayüz kontrolü (ikinci prototip açıkken): `node tests/windows-workspace-ui.mjs`.
Playwright geliştirme ortamında bulunmalıdır; gerekirse `APK_CLEANER_PLAYWRIGHT`
değişkeni mevcut Playwright modülünün import yolunu gösterebilir. Test, gerçek
işlem başlatmadan ekran geçişlerini, temaları, filtreyi ve iptal onayını denetler.
