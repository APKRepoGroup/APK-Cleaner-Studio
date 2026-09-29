# APK Cleaner Studio v0.6.2

<p align="center">
  <img src="release-assets/APK-Cleaner-Studio-README-Kapagi.png" alt="APK Cleaner Studio tanıtım kapağı" width="100%">
</p>

[English README](README-EN.md) · [Termux kurulumu](README-TERMUX.md) · [Kaynaktan derleme](BUILDING.md) · [v0.6.2 sürüm notları](RELEASE-NOTES-v0.6.2.md)

APK Cleaner Studio; APK, APKS, APKM ve XAPK paketlerini yerel olarak analiz eden, doğrulanmış reklam izlerini temizleyen ve split paketleri tek kurulabilir APK’da birleştiren bir Android paket işleme aracıdır. Kaynak paket değiştirilmez; bütün işlemler yeni bir çıktı dosyası üzerinde gerçekleştirilir.

**Kararlı sürüm:** v0.6.2 · **Motor:** 2.0 · **Platformlar:** Android, Windows ve Termux

## İndirme

Güncel kararlı paketleri [GitHub Releases](https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/latest) sayfasından indirebilirsin:

| Platform | Paket |
| --- | --- |
| Android | `APK-Cleaner-Studio-v0.6.2-Android.apk` |
| Windows | `APK-Cleaner-Studio-v0.6.2-Windows.exe` |
| Termux | `APK-Cleaner-Studio-v0.6.2-Termux.zip` |

İndirdiğin paketi aynı sürümle yayımlanan `SHA256-v0.6.2.txt` dosyasıyla doğrulayabilirsin. Yeniliklerin görsellerle anlatıldığı sürüm özeti [Telegraph sayfasında](https://telegra.ph/APK-Cleaner-Studio-v062--Kararl%C4%B1-S%C3%BCr%C3%BCm-Notlar%C4%B1-09-20) yer alır.

## Neler yapar?

- Yerleşik 18 mobil reklam SDK ailesini DEX, manifest, metadata, XML, asset ve native kütüphane izleri üzerinden denetler.
- Doğrulanmış reklam çağrılarını seçilen temizlik kapsamına göre güvenli biçimde etkisizleştirir.
- APKS, APKM ve XAPK içindeki taban, özellik ve yapılandırma split bileşenlerini tek imzalı APK’da birleştirir.
- Split paketlerde işlemci mimarisi, dil ve DPI bileşenlerinin seçilmesine izin verir.
- Başlangıç akışına sonradan eklenmiş olabilecek Toast, Snackbar, DialogFragment ve PopupWindow çağrılarını incelemeye sunar.
- Android’de cihazda yüklü uygulamaları simgesi, paket adı ve sürüm numarasıyla listeler; seçilen uygulamayı paylaşabilir veya doğrudan işleme alabilir.
- İşlem raporlarını, çıktı dosyalarını ve geçmiş işlemleri aynı yerel arayüzden yönetir.
- Açık, koyu ve sistem temalarını destekler; masaüstü ve mobil ekranlara uyum sağlar.

Dosyalar en fazla 1 GB olabilir. Analiz ve düzenleme işlemleri kullanılan cihazda gerçekleşir; paketler harici bir sunucuya gönderilmez.

## İş akışı

1. Bir APK, APKS, APKM veya XAPK dosyası seçilir. Android sürümünde paket, **Yüklü uygulamalardan seç** düğmesiyle cihazdan da alınabilir.
2. Motor paketi tarar; reklam ağlarını, DEX dosyalarını, manifest kayıtlarını, XML adaylarını ve split bileşenlerini raporlar.
3. Uygulanacak işlem, temizlik kapsamı ve isteğe bağlı iyileştirmeler seçilir.
4. İşlem yeni bir dosya üzerinde yürütülür; sonuç APK’sı, ayrıntılı rapor ve işlem özeti hazırlanır.

İşlem sürerken iptal edilebilir. Orijinal paket hiçbir aşamada değiştirilmez.

## İşlem türleri

### Reklam izlerini temizle

Doğrulanmış DEX çağrılarını, manifest kayıtlarını ve XML reklam alanlarını seçilen profile göre düzenler. Normal reklam yaması, DEX üzerinde decompile işlemi yapmaz ve Smali/Baksmali ara kodu üretmez; hedef komut baytlarını mümkün olduğunda aynı uzunluğu koruyarak yerinde değiştirir.

Reklam temizliği zorunlu değildir. Analizde doğrulanmış bir reklam ağı bulunmazsa profil kartları devre dışı kalır; bağımsız iyileştirmeler yine kullanılabilir.

### Tek APK oluştur

APKS, APKM veya XAPK paketindeki split modülleri tek kurulabilir APK’da birleştirir. Uygun paketlerde işlemci mimarisi, dil ve DPI bileşenleri ayrı ayrı seçilebilir. Reklam temizliği bu işlemden bağımsızdır; istenirse **Dönüştürme sırasında reklam yaması uygula** seçeneğiyle aynı çıktıya eklenebilir.

## Temizlik kapsamları

- **Güvenli:** Yalnızca doğrulanmış reklam yükleme ve gösterme çağrılarını etkisizleştirir. En az müdahale gerektiren profildir.
- **Dengeli:** Güvenli profile ek olarak manifest kayıtlarını ve doğrulanmış XML reklam alanlarını düzenler. Varsayılan ve önerilen seçenektir.
- **Gelişmiş:** Dengeli profile ek olarak kesin eşleşen reklam asset ve native SDK kalıntılarını hedefler.

Dengeli ve Gelişmiş profillerde, bilinen reklam görünümü taşıyan `res/layout*.xml` öğeleri `0dp` ve `gone` kullanılarak gizlenir. Nesne döndüren ve otomatik olarak değiştirilmesi uygulamayı bozabilecek riskli çağrılar yalnızca raporlanır.

## Başlangıç mesajlarını incele

Motor; Activity, Fragment ve Application sınıflarının `onCreate`, `onResume` ve benzeri başlangıç yollarından ulaşılan mesaj çağrılarını inceler. Toast, Snackbar, DialogFragment ve PopupWindow gibi adaylar bağlamlarıyla birlikte listelenir.

Hiçbir aday otomatik olarak seçilmez. Yalnızca kullanıcının işaretlediği başlangıç çağrısı, aynı komut uzunluğu korunarak etkisizleştirilir; Activity gövdesi veya ortak `show()` yöntemleri topluca silinmez. Bir çağrının sonradan eklendiği, yalnızca APK incelenerek kesin biçimde kanıtlanamayacağı için son karar kullanıcıya bırakılır.

## İsteğe bağlı iyileştirmeler

Aşağıdaki dört seçenek reklam temizliğinden ve birbirinden bağımsızdır:

- **DEX hata ayıklama verilerini kaldır:** Kaynak dosya, satır, yerel değişken ve diğer hata ayıklama kayıtlarını temizler. Bu işlem seçildiğinde ilgili DEX dosyaları yeniden yazılır; Smali/Baksmali kullanılmaz.
- **DEX yapısını yeniden düzenle:** Standart DEX yapısını doğrular ve DexLib2 ile yeniden yazar. Eşleme dosyası olmadan özgün sınıf veya yöntem adlarını geri getirmez. Motor, DEX yapısını güvenli biçimde okuyamazsa bozuk bir çıktı üretmek yerine işlemi durdurur.
- **Yamalanan APK’yı optimize et:** İmzalamadan önce standart ZIP hizalaması uygular. DEX, manifest veya RES içeriğini yeniden derlemez; yalnızca APK içindeki dosyaların ZIP yerleşimini düzenler.
- **RES kaynak korumasını kaldır:** APKEditor’ün yalın `x` işlemini (`java -jar APKEditor.jar x -i giriş.apk -o çıkış.apk`) doğrudan uygular. `-fix-types` kullanılmaz; APKEditor’ün ürettiği paket sonraki aşamaya olduğu gibi aktarılır.

Split paket dönüşümünde ayrıca **Dönüştürme sırasında reklam yaması uygula** seçeneği gösterilir. Bu seçenek, **Tek APK oluştur** işlemi tamamlanırken seçilen Güvenli, Dengeli veya Gelişmiş kapsamı aynı çıktıya uygular.

## Android

Android paketi `com.apkrepo.apkcleanerstudio` kimliğini ve `62` sürüm kodunu kullanır. En düşük Android sürümü Android 8.0’dır (API 26). v0.6.2 paketi, aynı kimliğe sahip v0.6.1 kurulumunun üzerine güncellenebilir.

Android sürümüne özgü özellikler:

- Cihazda yüklü uygulamaları ad, simge, paket kimliği ve sürüm numarasıyla arama ve seçme.
- Seçilen uygulamanın base APK’sını ve varsa split bileşenlerini birlikte hazırlama.
- Kaynak paketi Android paylaşım menüsüyle dışarı aktarma.
- Oluşturulan APK’yı indirme, paylaşma veya doğrudan sistem paket yükleyicisine gönderme.
- Yükleme öncesinde Android sürümü, işlemci mimarisi, mevcut kurulum ve olası imza çakışmalarını denetleme.
- WebView beklenmedik biçimde kapanırsa uygulamayı kapatmadan arayüzü yeniden açma.

## Windows

`APK-Cleaner-Studio-v0.6.2-Windows.exe` dosyasını çalıştırman yeterlidir. Ayrı bir Python kurulumu veya BAT dosyası gerekmez. Java ya da gerekli işlem bileşenleri eksikse arayüzdeki **Eksik bileşenleri hazırla** düğmesi, doğrulanmış taşınabilir araç zincirini kullanıcı klasörüne kurar.

Uygulama varsayılan olarak yerel ağda dinler. Konsolda bu bilgisayar için `127.0.0.1` adresi ve aynı güvenilir ağdaki diğer cihazlar için yerel ağ adresi gösterilir. LAN erişimi kimlik doğrulaması içermez; yalnızca güvendiğin özel ağlarda kullanılmalıdır.

Windows yerel arayüzü isteğe bağlı HTTPS ile çalışabilir. Yerel sertifikaya güven verildiğinde `127.0.0.1` bağlantısı HTTPS’e yükseltilir; sertifikanın özel anahtarı cihazdan çıkarılmaz. Telefonda HTTPS kullanmak için arayüzdeki **Yerel işlem motoru → Mobil HTTPS sertifikası** bölümünden CA sertifikası indirilebilir. Sertifika kurulmak istenmiyorsa yerel HTTP bağlantısı kullanılmaya devam edilebilir.

## Termux

ZIP paketini çıkardıktan sonra Termux’ta ilgili klasöre gir. Paket Android’in İndirilenler klasöründeyse örnek:

```bash
termux-setup-storage
cd ~/storage/downloads/APK-Cleaner-Studio-v0.6.2-Termux
```

İlk kurulumda bir kez:

```bash
bash install-termux.sh
```

Sonraki kullanımlarda:

```bash
bash start-termux.sh
```

Yükleyici, Termux deposunda bulunduğunda OpenJDK 25’i kullanır; cihaz mimarisi veya kullanılan depo bu paketi sunmuyorsa OpenJDK 21 ile devam eder. Termux:Widget kuruluysa ana ekran kısayolu da hazırlanır. Ayrıntılı kurulum bilgileri [README-TERMUX.md](README-TERMUX.md) dosyasındadır.

## Raporlar, geçmiş ve yerel veriler

- Sonuç ekranında **Raporu aç**, **Paylaş**, **APK’yı kur** ve **APK’yı indir** seçenekleri, platformun desteklediği ölçüde gösterilir.
- Çıktı sunulmadan önce APK arşivinin CRC bütünlüğü, manifest ve DEX kayıtları, native kütüphaneleri ve imzası doğrulanır. Split paketlerde seçilen modüller birleştirmeden önce denetlenir.
- İşlem raporu, değişen DEX dosyalarının önce/sonra boyutunu ve SHA-256 değerini, kaldırılan manifest kayıtlarını ve XML alanlarının eski/yeni değerlerini gösterir.
- Sık kullanılan işlem seçenekleri **Kayıtlı işlem profilleri** bölümünde saklanabilir. Bu profillere kaynak APK, dosya adı veya kullanıcı verisi eklenmez; kayıtlar yalnızca kullanılan cihazın tarayıcı alanındadır.
- Tamamlanan işlemler yeniden açılabilir; rapor ve çıktı hazırsa doğrudan görüntülenebilir veya indirilebilir.
- Kaynak paketler, raporlar ve çıktılar 14 gün boyunca yalnızca yerel cihazda tutulur. İstenmeyen kayıtlar geçmiş listesinden silinebilir.
- Yerel ağ oturumları 10 saniyede bir yenilenir; bağlantısı kesilen cihazlar 5 dakika sonra listeden kaldırılır. Verilen görünen ad yalnızca uygulamanın çalıştığı cihazda saklanır.

## Sınırlar ve güvenlik

- Her APK’da yüzde yüz otomatik ve sorunsuz reklam temizliği garanti edilemez.
- Yeniden imzalanan APK, mağaza sürümünün veya farklı anahtarla imzalanmış mevcut kurulumun üzerine yüklenemeyebilir.
- Universal APK üretimi, bazı isteğe bağlı özellik modüllerinde kaynak uygulamanın split varsayımlarına bağlıdır.
- Uygulama ücretli özellikleri, satın almaları, abonelikleri veya lisans kontrollerini atlatmak için tasarlanmamıştır.
- Yalnızca sahibi olduğun ya da değiştirme ve test etme yetkisine sahip olduğun paketlerde kullan.

## Lisans

APK Cleaner Studio, `Copyright (C) 2026 APK Repo Grubu` bildirimiyle GNU General Public License v3.0 kapsamında açık kaynak olarak yayımlanır. Uygulamayı lisans koşullarına uyarak kullanabilir, inceleyebilir, değiştirebilir ve yeniden dağıtabilirsin. Tam metin için [LICENSE](LICENSE) dosyasına bakabilirsin.

Üçüncü taraf bileşenler kendi lisanslarını korur; ayrıntılar [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) dosyasındadır.

Kaynak koddan derleme, yerel imzalama anahtarı oluşturma ve paketleme adımları için [BUILDING.md](BUILDING.md) dosyasına bakabilirsin.
