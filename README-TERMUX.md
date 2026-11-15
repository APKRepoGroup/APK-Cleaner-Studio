# APK Cleaner Studio — Termux

Bu paket Android/Termux sürümüdür. Windows EXE içermez. Paket sürümü `VERSION.txt` dosyasında yazılıdır.

## İlk kurulum

1. ZIP paketini telefonunda bir klasöre çıkar.
2. Termux’u aç ve ilk kez ortak depolamaya erişeceksen aşağıdaki komutu çalıştırıp izni onayla:

```bash
termux-setup-storage
```

3. `cd` komutuyla ZIP’i çıkardığın APK Cleaner Studio klasörüne gir. Örneğin paketi Android’in **Download/İndirilenler** klasörüne çıkardıysan, aşağıdaki `PAKET_KLASÖRÜ` yerine kendi klasörünün adını yaz:

```bash
cd "$HOME/storage/downloads/PAKET_KLASÖRÜ"
```

Klasörün adı veya konumu farklıysa kendi tam klasör yolunu kullan:

```bash
cd "/paketi/çıkardığın/tam/klasör/yolu"
```

4. Doğru klasöre girdikten sonra kurulumu bir kez çalıştır:

```bash
bash install-termux.sh
```

5. Sonraki kullanımlarda yine aynı klasöre `cd` ile girip uygulamayı başlat:

```bash
bash start-termux.sh
```

`install-termux.sh` veya `start-termux.sh` komutlarını paketin bulunduğu klasöre girmeden çalıştırırsan Termux dosyayı bulamaz.

## İsteğe bağlı iyileştirmeler

- **Dönüştürme sırasında reklam yaması uygula:** APKS, APKM veya XAPK paketini tek APK’ya dönüştürürken seçilen reklam temizleme profilini de çalıştırır.
- **DEX hata ayıklama verilerini kaldır:** Kaynak dosya, satır ve yerel değişken gibi DEX hata ayıklama kayıtlarını temizler. Smali/Baksmali kullanmaz.
- **Yamalanan APK’yı optimize et:** APK imzalanmadan önce standart ZIP hizalaması uygular. DEX, manifest ve RES içeriğini değiştirmez veya RES kaynaklarını yeniden korumalı hâle getirmez.
- **RES kaynak korumasını kaldır:** APKEditor’ün yalın `x` komutunu doğrudan uygular. `-fix-types` kullanılmaz ve manifest ya da diğer binary XML dosyaları sonradan geri yüklenmez.

Seçenekler bağımsızdır; kullanıcı yalnızca ihtiyaç duyduğu işlemleri etkinleştirebilir.

Başlangıç ekranı telefonun terminal genişliğine otomatik uyum sağlar. Tarayıcı aynı telefonda varsayılan olarak `http://127.0.0.1:8080/` adresini açar; böylece yerel CA sertifikası kurulmadan önce tarayıcı güvenlik uyarısı göstermez. HTTPS desteği aynı bağlantı noktasında etkin kalır. CA sertifikasını Android’e güvenilir olarak tanıtırsan arayüz kullanılabilir olduğunda bağlantıyı otomatik olarak HTTPS’e yükseltmeyi dener.

Termux oturumunu kapattığında yerel sunucu da sonlandırılır ve bağlantı noktası serbest bırakılır. Uygulamayı yeniden başlatırken önceki oturumdan kalmış geçerli bir süreç algılanırsa başlatıcı bu süreci güvenli biçimde kapatıp temiz bir oturum açar.

Yerel HTTPS kullanmak istersen arayüzde **Yerel işlem motoru → Mobil HTTPS sertifikası** bölümünü aç. CA sertifikasını indirip Android güvenlik ayarlarından bir kez **CA sertifikası** olarak yükle, ardından kullandığın tarayıcıyı tamamen kapatıp yeniden aç. Tarayıcı sertifikayı kabul etmezse yerel HTTP adresini kullanmaya devam edebilirsin. Sertifikayı yalnızca kendi güvendiğin cihazdan indir.

Kurulum güncel Termux deposunda bulunduğunda **OpenJDK 25** kullanır. Cihaz mimarisi veya depo OpenJDK 25 sunmuyorsa kurulum uyumluluğu korumak için OpenJDK 21’e geri döner.

Termux:Widget kuruluysa ilk kurulum **APK Cleaner Studio** ana ekran kısayolunu hazırlar. Arayüzde APK, APKS, APKM ve XAPK seçebilir; split paketi yalnızca dönüştürebilir veya reklam yamalarıyla birlikte işleyebilirsin.

Uygulamayı kapatmak için Termux ekranında `Ctrl+C` kullan. Başlatıcı kendi sunucu sürecini ve PID kaydını temizler. Beklenmeyen bir kapanıştan sonra yeniden başlatıldığında yalnızca APK Cleaner Studio’ya ait önceki süreç güvenli biçimde sonlandırılır.

Açık, sistem ve koyu tema tercihi tarayıcıda saklanır. İşlemler cihazdan dışarı çıkmaz.

> Termux kullanmak istemeyenler, GitHub Releases bölümündeki doğrudan kurulabilen Android APK paketini kullanabilir.
