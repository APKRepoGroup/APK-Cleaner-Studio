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

## Dev.7 ikinci grup — onaylandı ve uygulandı

- Karşılaştırmada yalnızca farkları gösterme ve iki APK'nın yerini değiştirme. Aynı sayıda ancak farklı içerikte izin/ağ kümeleri de fark sayılır. Yerel commit: `095037d`.
- Final paketlerden tek SHA-256 listesi ve dağıtım kaydı oluşturma; paket değişikliği ve eski checksum dosyalarını reddetme. `packaging/release_integrity.py prepare` ve `verify` final paketler hazır olduğunda kullanılacak. Yerel commit: `9829156`.
- Profil içe aktarma onayında etkin seçeneklerin, ad çakışmasının ve sürüm kodu uyarısının önizlenmesi. Başka sekmede değişen kayıtlar sessizce ezilmez; yeniden önizleme istenir.

Kontroller: 190 JavaScript testi geçti, seçilen 142 Python testinde hata yok (mevcut Android çıktı kontrolü atlandı). Üretim web çıktısı testi derleme yapılmadığı için çalıştırılmadı. Mobil ve kısa/yatay ekranlarda önizleme, klavye odağı, fark filtresi ve dosya yer değiştirme tarayıcıda kontrol edildi. SHA-256 otomasyonu yalnızca geçici test dosyalarıyla sınandı; gerçek final paket üretilmedi, hiçbir sürüm/GitHub kaydı değiştirilmedi.

## Dev.7 üçüncü grup — kullanıcı onayı

- İzinlerde manifestin Android API sınırları: `maxSdkVersion` ve `uses-permission-sdk-23` okunur; eski veya okunamayan kayıtlara sınır uydurulmaz. Birden fazla bildirim korunur. Metin ve ikili XML testleri eklendi. Yerel commit: `6234bc8`.
- Paket analizinde gerçek aşama/ilerleme ve iptal desteği: taranan DEX/kaynak sayısı ve mevcut aşama gösterilir. Yüzde süre tahmini değildir. İptal güvenli kontrol noktalarında gerçekleşir; çalışan araç adımının bitmesi gerekebilir. İptal edilen analizin geçici dosyaları temizlenir. Yama işleminin iptal akışından bağımsızdır.
- Android yüklü uygulama aktarımı da analize özgü kimlik ve iptal işareti taşır; başka bir işlem motoru veya Java aracı topluca durdurulmaz. Eski JSON analiz API'si korunur.

Kontroller: 197 JavaScript testi; seçilen 167 Python testi (166 geçti, APK çıktı kontrolü derleme olmadığı için atlandı). Gerçek yerel HTTP üzerinden analiz sürerken ilerleme sorgusu ve iptal isteği ayrıca doğrulandı. Lint temiz. Mobil 390 px ve masaüstü 1440 px görünümü örnek verilerle denetlendi. Android kaynakları eşitlendi; native köprüdeki değişiklikler final APK cihaz testinde ayrıca doğrulanacak.

Örnek analiz / iptal: `http://127.0.0.1:18087/?embedded=android&capture=dev7-analysis`. Gerçek dosya taramaz. İzin sınırları mevcut `dev7-permissions` ekranında da gösterilir.

Bu grup için de dağıtım derlemesi ve GitHub işlemi istenmedi.
