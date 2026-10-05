# 0.6.3-dev.4 (2026-10-06)

## ✨ Yeni Özellikler

- İşlem ekranına seçili uygulamayı gösteren bir bilgi çubuğu eklendi. APK, APKS, APKM ve XAPK paketlerinin uygulama simgeleri analiz ve ilerleme ekranlarında gösteriliyor; okunamayan simgeler için paket türü göstergesi korunuyor.
- İşlem ilerlemesine geçen süre ve ayrıntılı işlem geçmişi eklendi. Son adımlar doğrudan takip edilebiliyor; geçmişin tamamı açılır bölümden incelenebiliyor.
- İşleme başlamadan önce seçilen işlemleri ve isteğe bağlı iyileştirmeleri özetleyen bir alan eklendi.
- Sonuç ekranına dosya boyutu, paket adı ve sürüm kodunu karşılaştıran **Önce / Sonra** tablosu eklendi.
- Analiz ekranına **APK bilgileri ve uyumluluk** bölümü eklendi. Android sürüm gereksinimleri, hedef Android sürümü, işlemci mimarileri, izinler ve pakette bulunan imza türleri incelenebiliyor. İmza türünün gösterilmesi, imzanın doğrulandığı anlamına gelmiyor.
- Uygulamanın adını ve simgesini isteğe bağlı değiştirme özelliği eklendi. Boş bırakılan alanlar korunuyor; bu özellik tek başına veya temizleme ve klonlama işlemleriyle birlikte kullanılabiliyor.

## 🛠️ İyileştirmeler

- Android uygulaması Android 17 / API 37 hedefiyle güncellendi. Minimum Android 8.0 desteği ve mevcut ARM mimarileri korundu.
- Uygulama simgeleri yuvarlatılmış çerçevelere alındı; uzun dosya adları ve ayrıntılı bilgiler için mobil yerleşim iyileştirildi.
- Yeni bilgi ve özelleştirme bölümleri mevcut açılır menülerle aynı animasyon düzenini kullanıyor.
- Sonuç ayrıntıları, uygulanan ad ve simge değişikliklerini de gösterecek şekilde genişletildi.

## 🐛 Düzeltmeler

- Kaynak paket ile son çıktıdaki paket adı ve sürüm kodunun doğru karşılaştırılması için manifest okuma denetimleri güçlendirildi.
- Simge yükleme ve paket değiştirme sırasında eski bir seçimin yeni pakete aktarılmasını önleyen kontroller eklendi.
- Özel simgeler için dosya türü, boyut ve içerik doğrulaması eklendi. Ad ve simge değişiklikleri mevcut kaynak kayıtlarını ve ayrı seçilen klonlama/sürüm kodu ayarlarını koruyacak şekilde uygulanıyor.

> Test sürümü: Bu sürüm hatalar içerebilir. Kararlı sürümü tercih ediyorsanız v0.6.2'yi kullanmaya devam edebilirsiniz.

Tam değişiklik kaydı: `v0.6.3-dev.3...v0.6.3-dev.4`
