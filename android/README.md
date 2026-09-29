# APK Cleaner Studio · Android

Bu modül, Windows ve Termux sürümlerindeki ortak web arayüzünü uygulama içindeki WebView'e taşır. Python sunucusu, DEX/AXML yardımcıları, APKEditor ve APK imzalama bileşeni uygulama sürecinde gömülü çalışır; Termux, komut satırı, haricî Java veya ayrı tarayıcı gerekmez.

## Hedef paket

- Uygulama kimliği: `com.apkrepo.apkcleanerstudio`
- Sürüm adı: `0.6.3-dev.2`
- Sürüm kodu: `6302`
- Minimum Android: 8.0 / API 26
- Hedef mimariler: `arm64-v8a`, `armeabi-v7a`
- Paketlenen diller: varsayılan İngilizce ve Türkçe
- Paketlenen yoğunluklar: `xhdpi`, `xxhdpi`

Doğrudan dağıtılan APK, **Yüklü uygulamalardan seç** işlevinde başlatıcısı olmayan
paketleri de gösterebilmek için geniş paket görünürlüğü iznini kullanır. Google
Play dağıtımı planlanırsa bu izin ve yayın beyanı ayrıca değerlendirilmelidir.

## Derleme

PowerShell'de proje kökünden:

```powershell
.\android\build-android.ps1 -Variant Release
```

Betik her derlemeden önce `packaging/build_java_tools.py` ile Java işlem motorlarını kaynaklarından yeniler, ardından `packaging/sync_android.py` aracını çalıştırır. Böylece `studio/` altındaki ortak Python motoru, aynı web arayüzü ve güncel Java adaptörleri Android paketine taşınır. Masaüstü sürümünde yapılan ortak bir değişikliğin Android'e aktarılması tek komutla gerçekleşir.

Uygulama dağıtım imzası ve parola yapılandırması kaynak ağacının dışındaki yerel, korumalı imza dizininde tutulur. Bu özel anahtar gelecekteki bütün Android güncellemelerinde aynen korunmalı ve güvenli biçimde yedeklenmelidir. Anahtar ve parolalar Git tarafından izlenmez ve APK'nın içine eklenmez. Uygulama dağıtım imzası, işlenen APK çıktılarının imzalanmasında kullanılan gömülü anahtardan tamamen ayrıdır.

Android SDK bulunamazsa `ANDROID_SDK_ROOT`, Gradle bulunamazsa `APK_CLEANER_GRADLE_HOME` ayarlanabilir. Depodaki Gradle Wrapper üretildikten sonra betik onu otomatik kullanır.

## Güncelleme modeli

Uygulama, `APKRepoGroup/APK-Cleaner-Studio` deposunun GitHub Releases bölümünü kanalına göre denetler. Kararlı kurulumlara yalnızca yeni kararlı sürümler gösterilir. Bir dev sürümünü kuran kullanıcı daha yeni dev sürümlerini ve o serinin ardından yayımlanan kararlı sürümü alabilir. Draft kayıtları hiçbir kanalda gösterilmez. Android paketi yalnızca beklenen resmî asset adı, depo adresi ve GitHub SHA-256 digest'i eşleştiğinde indirilir. Paket kimliği, sürüm kodu ve imza doğrulandıktan sonra standart Android güncelleme ekranı açılır; Android güvenlik modeli gereği kullanıcı onayı olmadan sessiz kurulum yapılmaz.

Dev ve kararlı Android paketleri aynı `com.apkrepo.apkcleanerstudio` kimliğini ve aynı dağıtım imzasını kullanır. Dev etiketi yalnızca sürüm adında görünür; cihazda ikinci bir APK Cleaner Studio uygulaması oluşturulmaz. Temizleme motoru çalıştığı sürece ekranın otomatik kapanması geçici olarak engellenir ve işlem tamamlandığında normal uyku davranışı geri yüklenir.

Uygulama kabuğunda değişiklik gerekmeyen arayüz, profil ve Python motor güncellemeleri için derleme betiği ortak kaynakları yeniden eşitler. Android izinleri veya yerel Java katmanı değiştiğinde yeni APK yayımlanır.
