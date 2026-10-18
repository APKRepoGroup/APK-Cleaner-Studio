## 0.6.3-dev.5 — Geliştirme taslağı

### ✨ Yeni Özellikler

- Pil uyarısının açıklaması iki paragrafa ayrıldı. Kullanıcının seçimiyle Android'in pil optimizasyonu muafiyeti onayı doğrudan açılır; cihazda ayrı arka plan kısıtlaması kalırsa uyarı korunur ve uygulama ayarlarına erişim sunulur.

- Android'de uygulama arka plandayken tamamlanan veya başarısız olan işlemler için sonuç bildirimi eklendi. Bildirime dokunularak ilgili işin sonucu açılabilir. Bildirim izinleri ve kilit ekranı gizliliği korunur; arayüz açıkken ek bildirim gösterilmez.

- İşlem geçmişine uygulama/dosya/paket adına göre arama, durum filtreleri ve sayfalama eklendi. Arama yalnız son görünen kayıtlarda değil, saklanan ve erişim izni bulunan tüm işlemlerde yapılır.
  Durum seçimi, açık/koyu temayı izleyen ve ortak açılma/kapanma animasyonunu kullanan uygulama içi bir pencereye taşındı.

### 🐛 Hata Düzeltmeleri

- Android açılış ekranı cihazın açık/koyu temasını izler. Açık tema için arka plan, yazı ve sistem çubuğu renkleri eklendi; koyu temadaki mevcut renkler ve animasyon süreleri korundu.
  Android 12 ve sonrasında animasyondan önce görünen ayrı büyük logo kaldırıldı; animasyon başlangıcı ilk çizim/sistem katmanının kapanışıyla eşleştirildi.
  Animasyondan önce boş ekranda beklemeye yol açan Python hazırlığı ana iş parçacığından servis çalışanına taşındı; animasyon ilk çizimde başlatılırken motor arka planda hazırlanır.

- Özel Teşekkürler alanında uzun test kullanıcısı adı, diğer kartların ölçüleri değiştirilmeden mobil görünümde tek satıra sığdırıldı.

- Android'de analiz ve işlem ekranlarındaki uygulama simgelerinin çözünürlüğü artırıldı; simgelerin çerçeve içindeki hizası düzeltildi. Geçmişten yeniden açılan APK'ların eski küçük simge önizlemesi de yenilenir. Kurulu uygulama listesinin küçük simge önbelleği korundu.


- Android'de pil optimizasyonu veya arka plan kısıtlaması etkin olduğunda uyarı ve ayarlara erişim eklendi. Ayarlardan dönüşte durum yeniden denetlenir. Güncelleme paneliyle aynı X simgesi ve kapanış animasyonu kullanılarak uyarı yalnız o açılış için kapatılabilir; sonraki açılışta kısıtlamalar sürüyorsa yeniden görünür. Mobil görünümde açıklama, simgeli başlığın altında tam genişlikte ortalanır.

- İşlem adımları tek, sabit yükseklikte ve kaydırılabilir bir günlükte birleştirildi. Yeni adımlar takip edilirken eski kayıtları inceleyen kullanıcının kaydırma konumu korunur; son adıma tek dokunuşla dönülebilir. Kaydırma çubuğu diğer menülerle aynı otomatik gizlenme davranışını kullanır.

- İşlemi iptal etmeden önce kullanıcı onayı eklendi. Onay penceresi açıkken tamamlanan veya değişen işlemlere yanlışlıkla iptal isteği gönderilmesi önlendi.

- Android bildirimindeki “Durdur” eylemine onay eklendi. Kullanıcı onay vermeden motor kapatılmaz; arayüz yüklenemese bile onay ekranına erişilebilir.

- Tamamlanma ile iptal isteğinin çakıştığı durumlarda işlem sonucunun yeniden “İptal ediliyor” durumuna dönmesi engellendi.

- Ekran yeniden açıldığında devam eden işleme yeniden bağlanma ve işlem geçmişinden “İşleme dön” desteği eklendi. Motor kapanmışsa yarım kalan kayıtlar açık bir açıklamayla işaretlenir; işlem kendiliğinden yeniden çalıştırılmaz ve tamamlanmamış çıktılar hazır dosya olarak gösterilmez.

- İşlem öncesinde çıktı ve geçici çalışma alanlarının boş kapasitesi denetlenir. Kritik dolulukta işlem başlatılmaz; tahmini alan yetersizse veya kapasite okunamazsa devam etmeden önce uyarı ve onay gösterilir. Depolama yönetimine uyarıdan doğrudan erişilebilir.

- Art arda paket seçimlerinde geciken analiz yanıtlarının veya hatalarının son seçilen paketi değiştirmesi engellendi. Geçmiş kayıtları ve Android'den uygulama alma sonuçları da seçim kimliğiyle denetlenir; çalışan işlem yeni bir paket seçimiyle değiştirilemez.

- İşlem ekranında bağlantı kaybı ve geciken durum yanıtları açıkça gösterilir. Son ilerleme bilgileri korunur; yeniden bağlantı için işlem baştan çalıştırılmaz. Silinmiş veya erişim izni olmayan kayıtlar sonsuz beklemeye neden olmaz.

- İşleme yeniden bağlanıldığında işlem türü, temizlik profili, ek yamalar, klon adı, görünüm ve split seçimleri ilgili işin kayıtlı seçeneklerinden geri yüklenir. İşlem ekranına aynı ortak animasyonu kullanan “İşlem seçenekleri” alanı eklendi. Eski kayıtta seçenek bilgisi yoksa varsayılanlar önceki seçimler gibi sunulmaz.

- Tamamlanmamış veya başarısız işlerin çıktılarına eski/doğrudan indirme bağlantısıyla erişilmesi engellendi. Sonuç raporu yalnız tamamlanan işlerde sunulur; hata raporuna erişim korunur ve geçersiz çıktı yolları reddedilir.

Bu dosya yerel sürüm notu taslağıdır; sürüm henüz yayımlanmadı.
