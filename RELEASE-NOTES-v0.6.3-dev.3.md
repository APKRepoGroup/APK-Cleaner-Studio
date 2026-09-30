## 0.6.3-dev.3 (2026-09-30)

### ✨ Yeni Özellikler

- **Play Store güncellemesini kapat** seçeneği eklendi. İsteğe bağlı bu yama, sürüm kodunu yükselterek mağazada güncelleme olarak gözükmesini sınırlar. Paket adı ve sürüm adı korunur; orijinal sürüm kodu içeren uygulamaya dönüş yeniden kurulum gerektirir. ([1e4b7d4](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/1e4b7d4d7034575d9aee6c5a6dfb09ad43673ba3))
- İşlem sonuçlarına kaynak ve çıktı boyutu, işlem süresi, kullanılan temizlik profili ve doğrulama özeti eklendi. Ayrıntılar, varsayılan kapalı **İşlem ayrıntıları** bölümünden incelenebilir. ([aea3442](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/aea34423556d98770aee3e251a0dc6524af829e0))

### 🛠️ İyileştirmeler

- Güncelleme bildirimi mobil ekranlar için yeniden düzenlendi. Bildirim kapatılsa bile sonraki açılışta yeniden gösterilir; sürüm notları panel içinde açılıp kapatılabilir. ([e77e6d2](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e77e6d20fc81480e7cab94990cb29d24d3ab1e0f))
- Destekçiler, Depolama Yönetimi, Kurulum Geçmişi ve diğer açılır bölümler ortak animasyon süresiyle çalışır. Mobil HTTPS açıklaması, bileşen listesini sıkıştırmadan aynı kart içinde aşağı doğru genişler. ([6358b9d](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/6358b9de7ec8971f5c5623915c0a718b11cb5b73))
- Başarısız işlemlerde son işlem aşaması, hata açıklaması ve izlenebilecek adımlar ekranda kalıcı olarak gösterilir. ([c249f29](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/c249f296e9fc26fa3dbbd86926c30cf0bac92516))

### 🐛 Hata Düzeltmeleri

- Windows'ta işlem ilerlemesi okunurken durum dosyasının eşzamanlı güncellenmesinden kaynaklanan erişim hatası giderildi. ([26a0771](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/26a077145c949d6b06900cc9727c1a7bcccbb7d3))
- Gelişmiş temizlikte reklam klasöründeki DEX dosyaları kaldırıldığında işlem raporunun hata vermesi düzeltildi. Aynı adlı DEX dosyalarının farklı klasörlerde bulunması artık işlem dosyalarını çakıştırmaz. ([5325836](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/5325836e8803e8187b43b52ec6c1d93e9e3196d2))
- Arşiv, bağlantı, depolama, erişim ve Android işlem hataları için Türkçe kullanıcı açıklamaları eklendi; İngilizce araç hataları doğrudan kullanıcıya gösterilmez. ([e88bbfb](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e88bbfbe0ff4d2013372dd3dd00e6df2a826d906))
- BlueStacks üzerinde otomatik güncellemede görülen paket imzası karşılaştırma sorunu giderildi; APK doğrulama ve imza eşleştirme kontrolleri korunuyor. ([97d3a48](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/97d3a483ded775706064389b4edfafbb33737201))
- Gelişmiş temizlikte bilinçli kaldırılan reklam SDK kütüphanelerinin, çıktı doğrulamasında eksik native kütüphane hatası oluşturması düzeltildi. Beklenmeyen dosya kayıpları hâlâ reddedilir. ([46474e3](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/46474e301f2e8025a95e7cd41da7c516e3ae246c))
- Hata raporlarında güvenli hata açıklamaları artık korunuyor; hassas yollar ve imzalama bilgileri ayıklanmaya devam ediyor. ([faf8e1d](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/faf8e1dcfdc9405c85ef9d1800195680f6d3de55))
- Normal APK işlemlerinde, tek APK oluşturma seçeneği bulunmadığında klonlama kartının yanlış satıra yerleşmesi düzeltildi. ([7ace6c7](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/7ace6c75cdd582707b955c807c3566ea2a329ec0))
- Güncelleme panelinin sayfa yenilenirken ilk anda ekran dışında görünmesine neden olan konum sıçraması giderildi. ([bbf4a48](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/bbf4a4846215c59080277c58e058771208d4af0d))

> **Test sürümü:** Bu sürüm test amaçlıdır ve hatalar içerebilir. Özgün dosyalarınızın yedeğini saklayın. Play Store seçeneği mağaza ayarlarını değiştirmez; sürüm kodu karşılaştırmasına dayanır. Yeniden kurulum uygulama verilerinin kaybolmasına neden olabilir. Kararlı sürümü tercih ediyorsanız v0.6.2’yi kullanmaya devam edin.

**Tam değişiklik kaydı:** [v0.6.3-dev.2...v0.6.3-dev.3](https://github.com/APKRepoGroup/APK-Cleaner-Studio/compare/v0.6.3-dev.2...v0.6.3-dev.3)
