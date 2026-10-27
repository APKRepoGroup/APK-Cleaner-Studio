/* Manifest declarations describe requested capabilities, never a malware verdict.
 * Reference: https://developer.android.com/reference/android/Manifest.permission */
(() => {
  "use strict";
  const definitions = {
    INTERNET: ["İnternet erişimi", "Ağ bağlantıları kurabilir."],
    ACCESS_NETWORK_STATE: ["Ağ durumu", "Cihazın ağ bağlantısı hakkında bilgi alabilir."],
    ACCESS_WIFI_STATE: ["Wi-Fi durumu", "Wi-Fi bağlantısı hakkında sistemin izin verdiği bilgileri okuyabilir."],
    CHANGE_WIFI_STATE: ["Wi-Fi bağlantısını yönetme", "Android sürümünün izin verdiği Wi-Fi işlemlerini yapabilir."],
    POST_NOTIFICATIONS: ["Bildirim gönderme", "Uygulama bildirimleri gösterebilir; yeni Android sürümlerinde kullanıcı onayı gerekir."],
    CAMERA: ["Kamera erişimi", "İzin verildiğinde kamerayı fotoğraf veya video için kullanabilir.", "Hassas erişim"],
    RECORD_AUDIO: ["Mikrofon erişimi", "İzin verildiğinde mikrofondan ses kaydedebilir.", "Hassas erişim"],
    ACCESS_FINE_LOCATION: ["Hassas konum", "İzin verildiğinde cihazın hassas konumunu alabilir.", "Hassas erişim"],
    ACCESS_COARSE_LOCATION: ["Yaklaşık konum", "İzin verildiğinde cihazın yaklaşık konumunu alabilir.", "Hassas erişim"],
    ACCESS_BACKGROUND_LOCATION: ["Arka planda konum", "Uygulama kullanılmıyorken konum erişimi isteyebilir; ayrıca onay ve konum izni gerekir.", "Hassas erişim"],
    READ_CONTACTS: ["Kişileri okuma", "İzin verildiğinde kayıtlı kişi bilgilerini okuyabilir.", "Hassas erişim"],
    WRITE_CONTACTS: ["Kişileri değiştirme", "İzin verildiğinde kişileri ekleyebilir, düzenleyebilir veya silebilir.", "Hassas erişim"],
    GET_ACCOUNTS: ["Hesap listesini okuma", "Sistemin izin verdiği cihaz hesaplarını listeleyebilir; hesap parolalarını vermez.", "Hassas erişim"],
    READ_CALENDAR: ["Takvimi okuma", "İzin verildiğinde takvim kayıtlarını okuyabilir.", "Hassas erişim"],
    WRITE_CALENDAR: ["Takvimi değiştirme", "İzin verildiğinde takvim kayıtlarını değiştirebilir.", "Hassas erişim"],
    READ_SMS: ["SMS okuma", "Sistem ve kullanıcı izin verirse SMS iletilerini okuyabilir.", "Hassas erişim"],
    RECEIVE_SMS: ["SMS alma", "Sistem ve kullanıcı izin verirse gelen SMS iletilerini alabilir.", "Hassas erişim"],
    SEND_SMS: ["SMS gönderme", "Sistem ve kullanıcı izin verirse SMS gönderebilir; ücret oluşabilir.", "Hassas erişim"],
    READ_PHONE_STATE: ["Telefon durumu", "İzin verildiğinde telefon durumuna ilişkin sınırlı bilgilere erişebilir; kapsam Android sürümüne bağlıdır.", "Hassas erişim"],
    READ_CALL_LOG: ["Arama geçmişi", "Sistem ve kullanıcı izin verirse arama kayıtlarını okuyabilir.", "Hassas erişim"],
    CALL_PHONE: ["Telefon araması başlatma", "İzin verildiğinde numarayı arama ekranında onaylatmadan arama başlatabilir.", "Hassas erişim"],
    BODY_SENSORS: ["Vücut sensörleri", "Desteklenen cihazlarda izin verildiğinde nabız gibi sensör verilerine erişebilir.", "Hassas erişim"],
    ACTIVITY_RECOGNITION: ["Fiziksel aktivite", "İzin verildiğinde adım ve fiziksel aktivite bilgilerine erişebilir.", "Hassas erişim"],
    BLUETOOTH_SCAN: ["Bluetooth taraması", "İzin verildiğinde yakındaki Bluetooth cihazlarını tarayabilir.", "Hassas erişim"],
    BLUETOOTH_CONNECT: ["Bluetooth bağlantısı", "İzin verildiğinde eşleştirilmiş Bluetooth cihazlarıyla iletişim kurabilir.", "Hassas erişim"],
    NEARBY_WIFI_DEVICES: ["Yakındaki Wi-Fi cihazları", "İzin verildiğinde desteklenen Wi-Fi cihazlarını bulabilir ve onlarla bağlantı kurabilir.", "Hassas erişim"],
    READ_MEDIA_IMAGES: ["Fotoğrafları okuma", "İzin verildiğinde paylaşılan depolamadaki görsellere erişebilir; erişim seçilen öğelerle sınırlandırılabilir.", "Hassas erişim"],
    READ_MEDIA_VIDEO: ["Videoları okuma", "İzin verildiğinde paylaşılan depolamadaki videolara erişebilir; erişim seçilen öğelerle sınırlandırılabilir.", "Hassas erişim"],
    READ_MEDIA_AUDIO: ["Ses dosyalarını okuma", "İzin verildiğinde diğer uygulamaların oluşturduğu paylaşılan ses dosyalarını okuyabilir.", "Hassas erişim"],
    READ_MEDIA_VISUAL_USER_SELECTED: ["Seçilen fotoğraf ve videolar", "Kullanıcının seçerek izin verdiği fotoğraf ve videolara erişebilir.", "Hassas erişim"],
    READ_EXTERNAL_STORAGE: ["Depolamayı okuma", "Eski Android sürümlerinde ortak depolama dosyalarına erişebilir; yeni sürümlerde kapsamı sınırlı veya etkisizdir.", "Hassas erişim"],
    WRITE_EXTERNAL_STORAGE: ["Depolamaya yazma", "Eski Android sürümlerinde ortak depolamaya yazabilir; yeni sürümlerde bu izin aynı erişimi sağlamaz.", "Hassas erişim"],
    MANAGE_EXTERNAL_STORAGE: ["Tüm dosyalara erişim", "Ayrı sistem onayıyla ortak depolamanın geniş bir bölümüne erişim isteyebilir; diğer uygulamaların özel verilerine sınırsız erişim sağlamaz.", "Özel erişim"],
    REQUEST_INSTALL_PACKAGES: ["Paket kurulumu isteme", "Android kurulum ekranını açabilir; bilinmeyen uygulama kaynağı izni ve kullanıcı onayı gerekebilir.", "Özel erişim"],
    SYSTEM_ALERT_WINDOW: ["Diğer uygulamaların üzerinde gösterme", "Ayrı sistem onayıyla diğer uygulamaların üzerinde pencere gösterebilir.", "Özel erişim"],
    REQUEST_IGNORE_BATTERY_OPTIMIZATIONS: ["Pil optimizasyonundan muafiyet isteme", "Kullanıcıdan pil optimizasyonu muafiyeti isteyebilir; tek başına kısıtlamaları kaldırmaz."],
    VIBRATE: ["Titreşim", "Cihazın titreşim özelliğini kullanabilir."],
    WAKE_LOCK: ["Cihazı uyanık tutma", "İşlem sürerken işlemcinin veya ekranın uykuya geçmesini engelleyebilir."],
    RECEIVE_BOOT_COMPLETED: ["Açılış bildirimi alma", "Cihaz açıldıktan sonra sistemden bildirim alabilir; arka plan sınırları yine geçerlidir."],
    FOREGROUND_SERVICE: ["Ön plan hizmeti", "Android kuralları dahilinde kullanıcıya bildirim gösteren bir hizmet çalıştırabilir."],
  };
  function describe(name) {
    const key = String(name || "");
    const short = key.startsWith("android.permission.") ? key.slice(19) : "";
    const known = Object.hasOwn(definitions, short) ? definitions[short] : null;
    if (known) return { name: key, title: known[0], description: known[1], category: known[2] || "Standart erişim" };
    return { name: key, title: short ? "Sistem izni" : "Uygulamaya özel izin", category: "Açıklama bulunamadı",
      description: short ? "Bu izin için yerel açıklama bulunmuyor. İşlevi, Android sürümüne ve uygulamanın kullanımına göre değerlendirilmelidir."
        : "Uygulama veya bir kütüphane tarafından tanımlanmış olabilir. Yalnızca adından erişim kapsamı belirlenemez." };
  }
  function scopeText(declarations) {
    if (!Array.isArray(declarations) || !declarations.length) return "Android sürüm sınırları bu analizde kaydedilmemiş.";
    const versions = { 23: "6", 24: "7", 25: "7.1", 26: "8", 27: "8.1", 28: "9", 29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14", 35: "15", 36: "16" };
    const api = value => Object.hasOwn(versions, value) ? `Android ${versions[value]} (API ${value})` : `API ${value}`;
    const valid = value => Number.isInteger(value) && value >= 1 && value <= 10000;
    return [...new Set(declarations.map(item => {
      if (!valid(item?.min_sdk)) return "Android sürüm sınırları okunamadı";
      if (item.bounds_known !== true || item.max_sdk !== null && !valid(item.max_sdk)) return "Üst API sınırı okunamadı";
      if (item.max_sdk !== null && item.max_sdk < item.min_sdk) return "Geçerli bir API aralığı bildirilmemiş";
      if (item.min_sdk === 1) return item.max_sdk === null ? "Ek API sınırı belirtilmemiş" : `En fazla ${api(item.max_sdk)}`;
      return item.max_sdk === null ? `${api(item.min_sdk)} ve sonrası` : `${api(item.min_sdk)} — ${api(item.max_sdk)}`;
    }))].join(" veya ");
  }
  globalThis.StudioPermissions = Object.freeze({ describe, scopeText });
})();
