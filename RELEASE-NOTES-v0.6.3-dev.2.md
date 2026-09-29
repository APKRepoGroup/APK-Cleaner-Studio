## 0.6.3-dev.2 (2026-09-29)

> **Ön sürüm:** Bu paketler test amaçlıdır; kararlı sürüm v0.6.2 olarak kalır. Özgün APK ve split paketlerin yedeğini saklayın.

### Android

- Gömülü araçların başarısız olduğu işlemlerde yalnızca `(1)` kodu yerine araç adı ve mevcutsa hata nedeni gösteriliyor.
- APKEditor çıktısının belleği sınırsız kullanması önlendi; Android'de DEX dosyaları daha düşük bellek yüküyle sırayla işleniyor.
- Önceki bir iptal işleminden kalabilen iş parçacığı kesintisi yeni işlemleri etkilemeyecek şekilde ele alındı.
- Sonuç ekranındaki **APK’yı kur** düğmesine kurulum simgesi ve dört kenarı eşit mavi çerçeve eklendi; indirme düğmesinin düz oku da uyumlu bir ikonla değiştirildi.
- Android'de APKS, APKM ve XAPK paketlerine **Doğrudan kur** seçeneği eklendi. Bu akış, arşivdeki özgün APK bileşenlerini tek APK'ya dönüştürmeden veya yeniden imzalamadan Android'in kurulum oturumuna gönderiyor; normal APK kurulumu değişmedi. OBB içeren XAPK paketleri bu akışta desteklenmiyor.
- Doğrudan kurulumda cihaza uygun ABI, ekran yoğunluğu ve dil split'leri otomatik öneriliyor; kullanıcı isterse zorunlu temel APK dışındaki bileşenleri elle seçebiliyor. Kurulumdan önce paket, sürüm ve seçilen bileşenlerin özeti gösteriliyor; Android'in kurulum hataları anlaşılır nedenlerle açıklanıyor.
- Başarısız işlemler için cihazda hata raporu hazırlanıyor. Kullanıcı raporu önizleyip isterse indiriyor; paket ve dosya adları varsayılan olarak gizli, yerel dosya yolları ile imzalama bilgileri rapor dışında. Android uygulamasının çökme, açılış ve WebView olayları için de kısa bir yerel kayıt tutuluyor; sistem genelindeki logcat toplanmıyor.
- Android'de doğrudan split kurulumlarının başarı, iptal ve hata sonuçları yerel **Kurulum Geçmişi** alanında nedenleriyle birlikte gösteriliyor.

### Çıktı güvenliği ve kullanım

- **APK’yı klonla** işlemi eklendi: özgün paket kimliğinden yeni bir ad öneriliyor; kullanıcı bunu elle düzenleyebiliyor. Manifestteki göreli bileşen sınıfları özgün sınıflarına bağlanıyor, çakışabilecek provider kimlikleri ayrıştırılıyor ve DEX’te yalnızca paket/sağlayıcı kimliğiyle birebir eşleşen sabitler güncelleniyor. `sharedUserId` veya kaynak referanslı provider kimliği gibi güvenle dönüştürülemeyen durumlarda işlem duruyor. Farklı paket adı kurulumda ayrı uygulama oluşturur; uygulamanın çalışması garanti edilemez.
- Sonuç sunulmadan önce APK arşivinin CRC bütünlüğü, manifest/DEX kayıtları, native kütüphaneler ve imza yeniden doğrulanıyor. Split modülleri birleştirme öncesinde denetleniyor.
- İşlem raporuna DEX dosyaları, manifest kayıtları ve XML alanları için önce/sonra ayrıntıları eklendi.
- Sık kullanılan işlem seçenekleri cihazda kayıtlı profiller olarak saklanabiliyor; APK dosyası veya dosya adı bu profillere dahil edilmiyor.
- **Depolama Yönetimi**, yerel kaynak, çıktı ve çalışma dosyalarının kapladığı alanı gösteriyor; kullanıcı seçtiği tamamlanmış işlem kayıtlarını ve ilişkili dosyalarını temizleyebiliyor. Devam eden işlemler korunuyor.
- Sonuç ekranındaki indirme/kurulum simgeleri, hata raporu düğmeleri ve dar ekran düzeni iyileştirildi. Masaüstünde depolama kartının alttaki içerikle çakışması giderildi.
- Özel Teşekkürler alanına @mrepomod, @Seckkk, @muharrem0001 ve @ByTECHNO ayrı **Test Ekibi** kartlarıyla eklendi; masaüstü ve mobil boşluklar düzenlendi.

### Paketler ve doğrulama

- `APK-Cleaner-Studio-v0.6.3-dev.2-Android.apk`
- `APK-Cleaner-Studio-v0.6.3-dev.2-Windows.exe`
- `APK-Cleaner-Studio-v0.6.3-dev.2-Termux.zip`
- `SHA256-v0.6.3-dev.2.txt`

173 Python birim testi, web arayüzü testleri ve lint, Windows/Termux paket denetimi ile Android APK içerik ve v2/v3 imza denetimi geçti. GitHub'daki dört dosyanın SHA-256 özetleri yayın sonrası ayrıca eşleştirilecektir.

Klonlama, uygulamanın kendi bütünlük denetimleri veya dış servis bağımlılıkları nedeniyle her uygulamada çalışmayabilir. Özgün split kurulumu OBB içeren XAPK paketlerini kapsamaz; Android kurulumu kullanıcı onayı gerektirir.
