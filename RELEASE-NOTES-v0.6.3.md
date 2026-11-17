## v0.6.3 — Kararlı sürüm

v0.6.2’den sonra yayımlanan dev.1–dev.7 sürümlerinin yeniliklerini, iyileştirmelerini ve hata düzeltmelerini bir araya getirir.

### ✨ Yeni Özellikler

- Android, Windows ve Termux için otomatik güncelleme ve ayrı kararlı/geliştirme kanalları eklendi. Paket adresi, boyutu ve SHA-256 değeri doğrulanır. ([841a024](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/841a024))
- Android’de APKS, APKM ve XAPK paketleri dönüştürülmeden ve yeniden imzalanmadan kurulabilir. Uygun split bileşenleri önerilir ve seçim onaya sunulur; OBB içeren XAPK’lar bu akışta desteklenmez.
- APK klonlama ve uygulama adını/simgesini özelleştirme seçenekleri eklendi. Bu işlemler temizlemeyle birlikte veya bağımsız kullanılabilir. ([412b106](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/412b106))
- İki APK’nın sürüm, paket adı, izin, mimari ve reklam ağı bilgileri karşılaştırılabilir; yalnızca farklar gösterilebilir ve dosyaların sırası değiştirilebilir. ([b9b9ba5](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/b9b9ba5), [095037d](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/095037d))
- İşlem seçenekleri profil olarak saklanabilir ve JSON ile taşınabilir. İçe aktarmadan önce seçenekler ve uyarılar gösterilir; mevcut kayıtlar korunur. ([95a4cf4](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/95a4cf4), [f6f7d9d](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/f6f7d9d))
- **APK bilgileri ve uyumluluk** bölümüne sürüm, mimari ve imza türü bilgileri eklendi. İzinler Türkçe açıklamaları ve Android sürüm sınırlarıyla gösterilir; imza türünün listelenmesi tek başına doğrulama değildir. ([0badee9](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/0badee9), [da4c172](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/da4c172), [6234bc8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/6234bc8))
- **Depolama Yönetimi**, doğrudan split kurulumları için **Kurulum Geçmişi** ve işlem geçmişinde arama/sayfalama/durum filtreleri eklendi. ([03a8808](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/03a8808))
- Başarısız işlemler için uygulamada incelenip indirilebilen hata raporları eklendi. Hassas dosya ve paket bilgileri varsayılan olarak gizlenir.
- **Play Store güncellemesini kapat** seçeneği eklendi. Paket adı ve sürüm adı korunarak sürüm kodu yükseltilir; eski koda dönüş yeniden kurulum gerektirebilir. Mağaza güncellemelerinin kesin olarak engellenmesi garanti edilmez. ([1e4b7d4](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/1e4b7d4))

### 🛠️ İyileştirmeler

- Windows sürümü konsol veya tarayıcı sekmesi yerine kendi penceresinde açılır. Pencere boyutu ve konumu hatırlanır; tekrar başlatıldığında mevcut pencere öne gelir. ([fa55565](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/fa55565))
- Windows görev çubuğunda ilerleme gösterilir. Sonuç bildirimleri ayarlanabilir ve bildirime tıklanınca ilgili sonuç açılır. ([2a98c9e](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/2a98c9e), [464d757](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/464d757))
- Yerel ağ erişimi isteğe bağlı açılır; cihazlar geçici kodla eşleştirilir ve oturumlar yönetilebilir. Bağlantı, port ve izin hataları Türkçe açıklanır. ([a05d02c](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/a05d02c))
- Son kayıt klasörü hatırlanır; kaydedilen APK Dosya Gezgini’nde gösterilebilir. ([262a348](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/262a348), [fc43529](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/fc43529))
- Analiz ilerlemesi izlenebilir ve analiz iptal edilebilir. İşlem ekranında uygulama simgesi, seçilen seçenekler, geçen süre ve kaydırılabilir tek günlük gösterilir. ([2388760](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/2388760), [f422ddd](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/f422ddd), [dee7e10](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/dee7e10))
- Sonuç ekranına **Önce / Sonra** karşılaştırması, işlem süresi, temizlik profili ve ayrıntılı değişiklik/doğrulama özeti eklendi. ([491a814](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/491a814), [aea3442](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/aea3442))
- Android’de pil kısıtlaması uyarısı ve sistem onayıyla arka plan izni isteme desteği eklendi. İşlem sırasında ekran açık tutulur; sonuç bildiriminden işleme dönülebilir. ([e489cb8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e489cb8), [d9cc020](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/d9cc020))
- Android 17 / API 37 hedeflenir; minimum Android 8.0 ve iki ARM mimarisi korunur. Açılış animasyonu cihaz temasına uyar ve motor arka planda hazırlanır. ([453cb06](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/453cb06), [c5692a5](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/c5692a5))
- Güncelleme notları bildirim içinden okunabilir; kapatılan bildirim sonraki açılışta yeniden gösterilir. İşlem iptali ve Android bildirimindeki motoru durdurma eylemi onay gerektirir. ([e77e6d2](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e77e6d2), [64e8ae8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/64e8ae8))
- GitHub ve Patreon bağlantıları eklendi; mobil kartlar, destekçiler ve test ekibi alanları düzenlendi. Uygulama, pencere ve sekme simgelerinin görünümü iyileştirildi. ([afb52e8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/afb52e8))

### 🐛 Hata Düzeltmeleri

- Gelişmiş temizlikte kaldırılan DEX/native dosyalarının doğrulamayı bozması ve farklı klasörlerdeki aynı adlı DEX dosyalarının çakışması düzeltildi. DEX işleme sırasında bellek kullanımı azaltıldı. ([5325836](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/5325836), [46474e3](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/46474e3))
- Paket seçimi ve iptal sırasında eski yanıtların yeni işlemi etkilemesi önlendi. Bağlantı kesintilerinde ilerleme korunur; devam eden işleme yeniden dönülebilir. ([b3d032f](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/b3d032f), [64e8ae8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/64e8ae8))
- Windows durum dosyalarındaki eşzamanlı erişim ve tamamlanma/iptal çakışmaları düzeltildi. Başarısız veya tamamlanmamış çıktılar indirmeye açılmaz. ([26a0771](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/26a0771), [64e8ae8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/64e8ae8))
- Arşiv, bağlantı, depolama ve araç hataları için Türkçe açıklamalar geliştirildi. Hata aşaması ve çözüm bilgileri ekranda korunur; Android açılış/WebView olayları yerelde kaydedilir. ([e88bbfb](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e88bbfb), [c249f29](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/c249f29))
- Android güncellemelerindeki imza karşılaştırması, APK paylaşımındaki dosya adları ve yüklü uygulama simgelerinin çözünürlüğü düzeltildi. Windows’ta desteklenen katmanlı ve vektör simgeler doğru gösterilir. ([97d3a48](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/97d3a48), [8e35f31](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/8e35f31))
- Dar pencerelerdeki taşmalar, yan panel sıçramaları ve işlem kartlarının hizası düzeltildi. Açık temadaki açılır pencere arka planı ve panel animasyonları iyileştirildi. ([afb52e8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/afb52e8))
- Depolama ve kurulum geçmişi önceden yüklenir; geciken depolama sorgusu yeniden denenebilir. ([afb52e8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/afb52e8))
- Windows güncelleme bağlantısı güçlendirildi; başarısız denetimler gösterilir ve yeniden denenebilir. ([5d303c1](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/5d303c1))
- İşlem öncesi boş alan kontrolü ve kritik dolulukta başlatma engeli eklendi. Depolama dolduğunda yarım çıktılar temizlenir; işlem hata durumuna geçer ve yeniden denenebilir. ([1d051d7](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/1d051d7), [b7e2c18](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/b7e2c18))
- Çıktı bütünlüğü ve imza denetimleri güçlendirildi. Final paketler SHA-256 listesiyle eşleştirilir; eski veya değişmiş dosyalar reddedilir. ([9829156](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/9829156))
- Termux kurulum bilgileri güncellendi; gereksiz Windows dosyaları, yinelenen Android metin kaynakları ve eski kaynak kalıntıları temizlendi. ([25e3976](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/25e3976))

**Tam değişiklik kaydı:** [v0.6.2...v0.6.3](https://github.com/APKRepoGroup/APK-Cleaner-Studio/compare/v0.6.2...v0.6.3)
