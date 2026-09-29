## 0.6.3-dev.2 (2026-09-29)

### ✨ Yeni Özellikler

- Android’de APKS, APKM ve XAPK paketleri, tek APK’ya dönüştürülmeden ve yeniden imzalanmadan doğrudan kurulabiliyor. OBB içeren XAPK paketleri bu akışta desteklenmiyor.
- Doğrudan kurulumda cihaza uygun split bileşenleri otomatik öneriliyor; kullanıcı zorunlu temel APK dışındaki bileşenleri elle seçebiliyor. Kurulum öncesinde seçim özeti gösteriliyor.
- **APK’yı klonla** özelliği eklendi. Önerilen paket adı elle değiştirilebiliyor; güvenle dönüştürülemeyen durumlarda işlem durduruluyor.
- Başarısız işlemler için cihazda önizlenip indirilebilen hata raporu eklendi. Paket ve dosya adları varsayılan olarak gizleniyor.
- Doğrudan split kurulumlarının sonuçlarını ve nedenlerini gösteren **Kurulum Geçmişi** eklendi.
- İşlem seçeneklerini APK dosyasından bağımsız olarak saklayan profiller eklendi.
- Kaynak, çıktı ve çalışma dosyalarının kapladığı alanı gösteren **Depolama Yönetimi** eklendi. Tamamlanmış işlemlerin kayıtları ve ilişkili dosyaları kullanıcı seçimiyle temizlenebiliyor.
- Özel Teşekkürler alanına @mrepomod, @Seckkk, @muharrem0001 ve @ByTECHNO ayrı **Test Ekibi** kartlarıyla eklendi.

### 🛠️ İyileştirmeler

- Android’de araç hataları yalnızca `(1)` koduyla değil, araç adı ve mevcutsa hata nedeniyle gösteriliyor.
- DEX işleme sırasında bellek kullanımı düşürüldü; önceki bir iptalden kalan iş parçacığı kesintisinin yeni işlemleri etkilemesi önlendi.
- İşlem bitmeden önce APK bütünlüğü, manifest ve DEX kayıtları, native kütüphaneler ve imza yeniden doğrulanıyor. Split modülleri de birleştirilmeden önce denetleniyor.
- İşlem raporuna DEX, manifest ve XML değişiklikleri için önce/sonra ayrıntıları eklendi.
- Sonuç ekranındaki kurulum ve indirme simgeleri, hata raporu düğmeleri ve dar ekran düzeni iyileştirildi. Masaüstünde depolama kartının diğer içerikle çakışması giderildi.
- Android uygulamasının çökme, açılış ve WebView olayları için kısa bir yerel kayıt eklendi; sistem genelindeki logcat toplanmıyor.


> **Test sürümü:** Bu sürüm test amaçlıdır ve hatalar içerebilir. APK klonlama her uygulamada çalışmayabilir; özgün dosyalarınızın yedeğini saklayın. Kararlı sürümü tercih ediyorsanız v0.6.2’yi kullanmaya devam edin.

**Tam değişiklik kaydı:** [v0.6.3-dev.1...v0.6.3-dev.2](https://github.com/APKRepoGroup/APK-Cleaner-Studio/compare/v0.6.3-dev.1...v0.6.3-dev.2)
