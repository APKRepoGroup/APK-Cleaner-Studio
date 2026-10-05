# APK Cleaner Studio — Kaynaktan derleme

Bu belge APK Cleaner Studio kaynak ağacını doğrulamak ve Android, Windows veya Termux paketlerini yeniden üretmek isteyen geliştiriciler içindir. Üretilen dosya adlarındaki sürüm, kökteki `VERSION.txt` değerinden alınır.

## Kaynak ağacında bulunmayan özel dosyalar

Depoda hiçbir gerçek yayın anahtarı, API anahtarı, token, parola dosyası veya yerel TLS özel anahtarı tutulmaz. Aşağıdaki dosyalar bilinçli olarak Git dışında bırakılır:

- `studio/tools/output-signing.p12`
- `android/app/src/main/assets/output-signing.p12`
- `android/signing/*.jks` ve `android/signing/*.p12`
- `android/signing.properties`
- `.env*`, `work/`, `studio/tls/` ve yerel derleme klasörleri

İşlenen APK çıktıları için kendi yerel anahtarını oluştur. Aşağıdaki geliştirme anahtarı yalnızca kendi derlemelerin içindir; resmî APK Cleaner Studio çıktılarıyla aynı imza kimliğini üretmez:

```powershell
keytool -genkeypair -alias apkcleaner-output -keyalg RSA -keysize 2048 -validity 36500 -storetype PKCS12 -keystore studio/tools/output-signing.p12 -storepass apkcleaner -keypass apkcleaner -dname "CN=APK Cleaner Studio Local Output,O=Local Build"
```

`packaging/sync_android.py` bu dosyayı Android varlıklarına kopyalar. Özel anahtarı hiçbir zaman Git deposuna ekleme.

Android uygulamasının kendi yayın imzası, çıktı imzalama anahtarından ayrıdır. Yayın anahtarı yapılandırması için [android/signing/README.md](android/signing/README.md) belgesini kullan.

## Web arayüzü ve testler

Gereksinimler:

- Node.js 22.13 veya daha yeni bir 22.x sürümü
- npm

```bash
npm ci
npm run lint
npm test
```

## Windows paketi

Gereksinimler:

- Python 3.11 veya daha yeni bir sürüm
- `cryptography`
- PyInstaller
- JDK 21 veya daha yeni bir sürüm

```powershell
python -m pip install cryptography pyinstaller
python -m PyInstaller packaging/APK-Cleaner-Studio-Windows.spec --noconfirm
```

Üretilen Windows paketi `dist/` altında oluşturulur. Taşınabilir Java ve işlem araçları eksikse uygulama ilk çalıştırmada **Eksik bileşenleri hazırla** akışıyla bunları kullanıcı alanında hazırlar.

## Android paketi

Gereksinimler:

- JDK 21
- Android 17 SDK (API 37) ve güncel build-tools
- Gradle veya Gradle Wrapper
- Python 3
- Yerel çıktı imzalama anahtarı

Proje kökünde PowerShell ile:

```powershell
./android/build-android.ps1 -Variant Release
```

`ANDROID_SDK_ROOT`, `APK_CLEANER_GRADLE_HOME`, `APK_CLEANER_ANDROID_JDK` ve `APK_CLEANER_PYTHON` ortam değişkenleri gerektiğinde özel araç yollarını göstermek için kullanılabilir. Çıktı `outputs/APK-Cleaner-Studio-v<SÜRÜM>-Android.apk` olarak hazırlanır ve imza ile ZIP hizalaması doğrulanır.

### Android 17 hedefi ve yayın öncesi doğrulama

Kaynak yapılandırması `compileSdk 37` ve `targetSdk 37` kullanır. Minimum Android sürümü değişmez: Android 8.0 (API 26). `arm64-v8a` ve `armeabi-v7a` desteği korunur; 32 bit desteğini kaldırmamak için gömülü Python 3.11 kullanılır.

Android kabuğu, kendi işlem motoruna aynı uygulama/profil içindeki `127.0.0.1` üzerinden bağlanır; LAN sunucusu açmaz. Bu nedenle bu akış için `ACCESS_LOCAL_NETWORK` izni eklenmez. HTTP istisnası yalnızca loopback adresleriyle sınırlıdır; dış HTTPS bağlantılarında platformun sertifika denetimleri kapatılmaz.

Chaquopy 17.0.0'ın Android Java köprüsü temel yerel kütüphaneleri `System.loadLibrary` ile kurulu APK'dan yükler. Uygulamanın Java kaynaklarında yazılabilir çalışma klasöründen `System.load` çağrısı yoktur. Android 17'nin yerel dinamik kod yükleme kısıtları nedeniyle bu durum, bağımlılık güncellemelerinde yeniden kontrol edilmelidir. Kullanıcının işlem dosyalarını veya tüm Python çalışma alanını salt okunur yapmak uygun bir çözüm değildir.

Hedef SDK değişikliği tek başına cihaz uyumluluğunu doğrulamaz. Son Android derlemesinden sonra aşağıdaki çalışma testleri yapılmadan Android 17 desteği tam doğrulanmış sayılmaz:

- Temiz kurulum ve önceki sürümün üzerine güncelleme; ilk ve sonraki açılışlarda Python motoru ve WebView bağlantısı.
- APK ve split paket analizi; dengeli/gelişmiş temizlik, klonlama, imzalama, çıktı doğrulama ve iptal.
- Çıktı paylaşımı/kurulumu, özgün split kurulumu ve otomatik güncellemenin kurulum onayı.
- Geri hareketi, döndürme, büyük ekran/pencere boyutlandırma, arka plana geçiş ve motorun yeniden başlatılması.
- Android 17 cihazında bellek baskısı ve mümkünse 16 KB sayfalı cihazda Python'un yerel modüllerinin yüklenmesi; ayrıca eski Android sürümlerinde gerileme testi.

Bu kontrol listesi tamamlanana kadar çalışma testlerinin durumu **beklemede** olarak değerlendirilir. Resmî gereksinimler: [Android 17 davranış değişiklikleri](https://developer.android.com/about/versions/17/behavior-changes-17), [tüm uygulamaları etkileyen değişiklikler](https://developer.android.com/about/versions/17/behavior-changes-all) ve [Chaquopy sürüm değişiklikleri](https://chaquo.com/chaquopy/doc/current/changelog.html).

## Termux paketi

Python 3 ile:

```bash
python packaging/build_termux.py
```

Çıktı `outputs/APK-Cleaner-Studio-v<SÜRÜM>-Termux.zip` olarak oluşturulur.

## Sürüm bütünlüğü

Dağıtımdan önce üç platform paketi için SHA-256 değerlerini yeniden üret ve `SHA256-v<SÜRÜM>.txt` dosyasıyla birlikte paylaş. Kaynak ağacındaki geçici çalışma dosyaları ile yerel anahtarlar paketlere eklenmemelidir.
