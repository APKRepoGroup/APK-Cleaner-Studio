# Sonraki geliştirmeler

2026-10-21 tarihinde kullanıcı aşağıdaki üç genel öneriyi **dev.7 planlamasına** bıraktı. Dev.6'nın mevcut işlerine dahil değildir; dev.7'ye geçilirken kullanıcıya yeniden hatırlatılmalıdır. Bu, otomatik uygulama onayı değildir; kapsamı planlama sırasında netleştirilecektir.

1. **İki APK'yı karşılaştırma:** İki bağımsız dosyanın sürüm, paket adı, izin, mimari ve reklam ağı bulgularını karşılaştırma. Mevcut işlem öncesi/sonrası tablosundan ayrıdır.
2. **İzin açıklamalarını geliştirme:** Mevcut listedeki Türkçe açıklamaları genişletme, hassas erişimleri açıklama; iznin varlığını tek başına zararlılık göstergesi saymama.
3. **İşlem profillerini içe/dışa aktarma:** Yalnızca kayıtlı işlem seçeneklerini dosya ile cihazlar arasında taşıma; APK, özel simge, paket kimliği veya hesap/bulut aktarımı gerektirmeme.

Mevcut onaylı iki Windows işi bunlarla karıştırılmamalıdır: bildirim tercihi ve vektör simge desteği. Bu kayıt kendi başına zamanlanmış bildirim oluşturmaz.

## Dev.7 durumu — 27 Ekim 2026

Kullanıcı bu üç özelliğin uygulanmasını açıkça onayladı; henüz derleme alınmamasını istedi.

- İki APK karşılaştırması: ayrı analiz alanı; geçici yüklemeler temizlenir, geçmiş veya mevcut iş değişmez. Yerel commit: `b9b9ba5`.
- İzin açıklamaları: Türkçe açıklamalar, hassas/özel erişim etiketleri ve manifest bildirimi ile verilmiş izin ayrımı. Yerel commit: `da4c172`.
- Profil aktarımı: sürümlü JSON, 16 KB / 12 profil sınırı, onaylı ve mevcut kayıtları koruyan içe aktarma. Yerel commit: `95a4cf4`.

Android dosya kaydetme sistem ekranı ve gerçek APK akışı son cihaz testlerinde ayrıca doğrulanmalı. Dağıtım derlemeleri ve GitHub gönderimi/yayını yapılmadı. Kullanıcının sonraki ilaveleri bekleniyor.

Kontroller: 186 JavaScript testi geçti; lint temiz. Seçilen 130 Python testinde hata yok (129 geçti, mevcut Android çıktı paketi kontrolü derleme yapılmadığı için atlandı). Üretim web çıktısını isteyen test de yeni derleme yapılmaması nedeniyle çalışma listesinin dışında bırakıldı. 390 px mobil ve 1440 px masaüstü görünümünde karşılaştırma ve izin açıklamaları denetlendi; profil JSON indirmesi tarayıcıda doğrulandı.

Yerel örnek veri ekranları: `http://127.0.0.1:18087/?capture=dev7-desktop` ve `http://127.0.0.1:18087/?capture=dev7-mobile`. Bunlar gerçek APK işlemez; demo profil deposu gerçek kayıtlarla paylaşılmaz.
