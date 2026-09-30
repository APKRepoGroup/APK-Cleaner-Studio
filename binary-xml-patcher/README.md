# Binary XML Patcher

AndroidManifest.xml dosyasını metne dönüştürmeden doğrudan ikili AXML ağacında düzenler.

- Yalnızca seçili reklam bileşenlerini, metadata kayıtlarını ve reklam izinlerini kaldırır.
- `resources.arsc` dosyasını yeniden üretmez.
- Kalan resource reference değerlerinin tür ve kimliklerini yazma sonrasında tekrar doğrular.
- Kaynak başvurularını `@style/...` biçiminden farklı bir sayısal kimliğe dönüştürmez.
- İsteğe bağlı `--restrict-store-updates`, yalnızca `android:versionCode` değerini en az 2100000000 yapar; daha yüksek kodu düşürmez. Paket adı, `versionName` ve mevcut `versionCodeMajor` korunur. Sayısal olmayan sürüm alanlarında işlem güvenle durur.
- `--inspect-version`, yazma yapmadan sürüm kodu ve major alanını döndürür. Üretilen APK yeniden imzalanıp doğrulandıktan sonra Python motoru bu alanları tekrar denetler. Bu seçenek Play Store ayarlarını değiştirmez ve düşük kodlu APK'ya normal geri dönüşü engelleyebilir.
