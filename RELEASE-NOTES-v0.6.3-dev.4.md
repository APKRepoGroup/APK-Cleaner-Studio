## 0.6.3-dev.4 (2026-10-06)

### ✨ Yeni Özellikler

- İşlem ekranına seçili uygulamayı gösteren bir bilgi çubuğu eklendi. APK, APKS, APKM ve XAPK paketlerinin uygulama simgeleri analiz ve ilerleme ekranlarında gösteriliyor; okunamayan simgeler için paket türü göstergesi korunuyor. ([f422ddd](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/f422ddd096c6a0be5fae617015893533991e7700))
- İşlem ilerlemesine geçen süre ve ayrıntılı işlem geçmişi eklendi. Son adımlar doğrudan takip edilebiliyor; geçmişin tamamı açılır bölümden incelenebiliyor. ([6954fa0](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/6954fa01bca466b0da8df7d1602bf1bd09a2f0bf))
- İşleme başlamadan önce seçilen işlemleri ve isteğe bağlı iyileştirmeleri özetleyen bir alan eklendi. ([2b448be](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/2b448be77ced9f8576fc38b8a13d32a1661f731e))
- Sonuç ekranına dosya boyutu, paket adı ve sürüm kodunu karşılaştıran **Önce / Sonra** tablosu eklendi. ([491a814](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/491a81453c8e7e61f9a3d74efb127d5cc2d90c16))
- Analiz ekranına **APK bilgileri ve uyumluluk** bölümü eklendi. Android sürüm gereksinimleri, hedef Android sürümü, işlemci mimarileri, izinler ve pakette bulunan imza türleri incelenebiliyor. İmza türünün gösterilmesi, imzanın doğrulandığı anlamına gelmiyor. ([0badee9](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/0badee9db967662f5cd9ff5cf40be6bb9d8ee61c))
- Uygulamanın adını ve simgesini isteğe bağlı değiştirme özelliği eklendi. Boş bırakılan alanlar korunuyor; bu özellik tek başına veya temizleme ve klonlama işlemleriyle birlikte kullanılabiliyor. ([412b106](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/412b106d6ec2cc0408f585c1f0ba1f1062af0569))

### 🛠️ İyileştirmeler

- Android uygulaması Android 17 / API 37 hedefiyle güncellendi. Minimum Android 8.0 desteği ve mevcut ARM mimarileri korundu. ([453cb06](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/453cb060d7e9fe648f4a5e99d40c7fb4d00a3259))
- Uygulama simgeleri yuvarlatılmış çerçevelere alındı; uzun dosya adları ve ayrıntılı bilgiler için mobil yerleşim iyileştirildi.
- Yeni bilgi ve özelleştirme bölümleri mevcut açılır menülerle aynı animasyon düzenini kullanıyor.
- Sonuç ayrıntıları, uygulanan ad ve simge değişikliklerini de gösterecek şekilde genişletildi.

### 🐛 Hata Düzeltmeleri

- Kaynak paket ile son çıktıdaki paket adı ve sürüm kodunun doğru karşılaştırılması için manifest okuma denetimleri güçlendirildi. ([491a814](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/491a81453c8e7e61f9a3d74efb127d5cc2d90c16))
- Simge yükleme ve paket değiştirme sırasında eski bir seçimin yeni pakete aktarılmasını önleyen kontroller eklendi.
- Özel simgeler için dosya türü, boyut ve içerik doğrulaması eklendi. Ad ve simge değişiklikleri mevcut kaynak kayıtlarını ve ayrı seçilen klonlama/sürüm kodu ayarlarını koruyacak şekilde uygulanıyor.

> **Test sürümü:** Bu sürüm hatalar içerebilir. Kararlı sürümü tercih ediyorsanız v0.6.2'yi kullanmaya devam edebilirsiniz.

**Tam değişiklik kaydı:** [v0.6.3-dev.3...v0.6.3-dev.4](https://github.com/APKRepoGroup/APK-Cleaner-Studio/compare/v0.6.3-dev.3...v0.6.3-dev.4)
