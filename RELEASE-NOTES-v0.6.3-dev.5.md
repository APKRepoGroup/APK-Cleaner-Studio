## 0.6.3-dev.5 (2026-10-18)

### ✨ Yeni Özellikler

- Android'de pil kısıtlaması uyarısı ve sistem onayıyla arka planda çalışma izni isteme özelliği eklendi. ([e489cb8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/e489cb8aed617f8b7e1cee23cd4dd7b319a8ec6a))

- Android'de arka plandaki işlemler için sonuç bildirimi ve bildirime dokunarak ilgili işleme dönme desteği eklendi. ([d9cc020](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/d9cc02030729d1602165af07d77b22afba6c7ef2))

- İşlem geçmişine uygulama, dosya ve paket adına göre arama, sayfalama ve temaya uyumlu durum filtresi eklendi. ([03a8808](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/03a8808d28248ea390b5574a42be8e63f214cecc))

- İşlem öncesi boş alan kontrolü eklendi; yetersiz depolama için uyarı ve kritik dolulukta başlatma engeli getirildi. ([1d051d7](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/1d051d75e85ceda95f298252c94e66f3a99fcaf5))

### 🛠️ İyileştirmeler

- İşlem adımları, son adıma dönüş düğmesi ve otomatik gizlenen kaydırma çubuğu içeren tek günlükte birleştirildi. ([dee7e10](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/dee7e100cf214617099ba24314786d6f9db7a2ba))

- Devam eden işleme ekran yeniden açıldığında veya geçmişten dönülebilir; kayıtlı ayarlar **İşlem seçenekleri** bölümünde gösterilir. ([64e8ae8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/64e8ae8b9166ff7a94b3683fc1175b0fa1190d1c))

- Pil uyarısına animasyonlu, oturumluk kapatma eklendi; kısıtlamalar sürüyorsa sonraki açılışta yeniden gösterilir.

- Android açılış animasyonu cihazın açık/koyu temasına uyumlu hâle getirildi.

- Özel Teşekkürler alanında uzun kullanıcı adlarının mobil yerleşimi düzeltildi. ([322c85c](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/322c85cd6542b5b68d57ad99355ccf042ed512b5))

### 🐛 Hata Düzeltmeleri

- Android'de animasyondan önceki ayrı logo ve boş ekran beklemesi giderildi; motor animasyon sırasında hazırlanıyor. ([c5692a5](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/c5692a5a701d44d53d6be4f8b9f33f002531d8ef))

- Android'de uygulama simgelerinin bulanıklığı ve çerçeve hizası düzeltildi; eski geçmiş önizlemeleri yenilendi. ([bcac449](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/bcac4494a156e235689ed8bc2f9798a0c8c8f1df))

- İşlem iptaline onay eklendi; tamamlanma ve iptal isteklerinin çakışmasından kaynaklanan durum hataları düzeltildi. ([64e8ae8](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/64e8ae8b9166ff7a94b3683fc1175b0fa1190d1c))

- Android bildirimindeki **Durdur** eylemine motoru kapatmadan önce onay adımı eklendi. ([d9cc020](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/d9cc02030729d1602165af07d77b22afba6c7ef2))

- Paket seçimi, geçmişten açma ve Android'den uygulama alma sırasında eski yanıtların yeni seçimi bozması engellendi. ([b3d032f](https://github.com/APKRepoGroup/APK-Cleaner-Studio/commit/b3d032f07c7c0c45bc08b7ba11155fd41b79f86a))

- Bağlantı kesintilerinde ilerleme bilgileri korunur; yeniden bağlanma ve erişilemeyen kayıtlarda sonsuz bekleme sorunları düzeltildi.

- Yarım kalan işlemlerin durumu ve çıktı erişimi düzeltildi; başarısız veya tamamlanmamış çıktılar indirilebilir dosya olarak sunulmaz.

> **Test sürümü:** Bu sürüm hatalar içerebilir. Kararlı sürümü tercih ediyorsanız v0.6.2'yi kullanmaya devam edebilirsiniz.

**Tam değişiklik kaydı:** [v0.6.3-dev.4...v0.6.3-dev.5](https://github.com/APKRepoGroup/APK-Cleaner-Studio/compare/v0.6.3-dev.4...v0.6.3-dev.5)
