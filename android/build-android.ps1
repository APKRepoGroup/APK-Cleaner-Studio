[CmdletBinding()]
param(
  [ValidateSet("Debug", "Release")]
  [string]$Variant = "Debug",
  [string]$OutputName = "APK-Cleaner-Studio-v0.6.3-dev.4-Android.apk",
  [switch]$Offline
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Windows'taki JDK 25, SUBST yolunu tekrar uzun gerçek yola kanonikleştirip
# zipfs kapanışında AccessDeniedException üretiyor. SHA-256 doğrulanmış Temurin
# 21 LTS kısa yolu koruyor ve temiz Android derlemesini tekrarlanabilir kılıyor.
$JdkCandidates = @()
if ($env:APK_CLEANER_ANDROID_JDK) { $JdkCandidates += $env:APK_CLEANER_ANDROID_JDK }
$JdkCandidates += Get-ChildItem (Join-Path $ProjectRoot ".tools\temurin-21") -Directory -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending | Select-Object -ExpandProperty FullName
if ($env:JAVA_HOME) { $JdkCandidates += $env:JAVA_HOME }
$JdkCandidates += Get-ChildItem "C:\Program Files\Eclipse Adoptium\jdk-21*", "C:\Program Files\Microsoft\jdk-21*", "C:\Program Files\Java\jdk-21*" -Directory -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending | Select-Object -ExpandProperty FullName
$PreferredJdk = $JdkCandidates | Where-Object {
  $Java = Join-Path $_ "bin\java.exe"
  if (-not (Test-Path -LiteralPath $Java)) { return $false }
  $VersionText = (& $Java -version 2>&1) -join "`n"
  return $VersionText -match 'version "21\.'
} | Select-Object -First 1
if (-not $PreferredJdk) {
  throw "JDK 21 bulunamadı. Temurin 21 kur veya APK_CLEANER_ANDROID_JDK değişkenini JDK dizinine ayarla."
}
$env:JAVA_HOME = $PreferredJdk
$env:Path = "$(Join-Path $PreferredJdk 'bin');$env:Path"

$Python = $env:APK_CLEANER_PYTHON
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($PythonCommand) { $Python = $PythonCommand.Source }
}
if (-not $Python) { throw "Python bulunamadı. APK_CLEANER_PYTHON değişkenini bir Python 3 yolu olarak ayarla." }

$Sdk = $env:ANDROID_SDK_ROOT
if (-not $Sdk) { $Sdk = $env:ANDROID_HOME }
if (-not $Sdk) {
  $Sdk = Get-ChildItem "$env:LOCALAPPDATA\pnpm\store\v11\projects\*\work\android-toolchain\android-sdk" -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Sdk -or -not (Test-Path -LiteralPath $Sdk)) {
  throw "Android SDK bulunamadı. ANDROID_SDK_ROOT değişkenini ayarla veya Android Studio SDK'sını kur."
}

# Windows'un ZIP dosya sistemi uzun gerçek yollardaki JAR'ları kapatırken
# AccessDeniedException üretebiliyor. Gradle'a yalnızca bu derleme süresince iki
# kısa sanal sürücü sun; eşlemeler finally içinde her durumda kaldırılır.
if (-not $env:APK_CLEANER_SHORT_PATH_BUILD -and $ProjectRoot.Length -gt 80) {
  $Occupied = [System.IO.DriveInfo]::GetDrives().Name | ForEach-Object { $_.Substring(0, 1).ToUpperInvariant() }
  $Free = @("R", "S", "T", "U", "V", "W", "X", "Y", "Z") | Where-Object { $_ -notin $Occupied }
  if ($Free.Count -lt 2) { throw "Android derlemesi için iki boş kısa sürücü harfi bulunamadı." }
  $ProjectDrive = "$($Free[0]):"
  $SdkDrive = "$($Free[1]):"
  $PreviousSdkRoot = $env:ANDROID_SDK_ROOT
  try {
    & subst.exe $ProjectDrive $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "$ProjectDrive kısa proje yolu kurulamadı." }
    & subst.exe $SdkDrive $Sdk
    if ($LASTEXITCODE -ne 0) { throw "$SdkDrive kısa SDK yolu kurulamadı." }
    $env:APK_CLEANER_SHORT_PATH_BUILD = "1"
    $env:ANDROID_SDK_ROOT = "$SdkDrive\"
    & "$ProjectDrive\android\build-android.ps1" -Variant $Variant -OutputName $OutputName -Offline:$Offline
    return
  } finally {
    Remove-Item Env:APK_CLEANER_SHORT_PATH_BUILD -ErrorAction SilentlyContinue
    if ($null -eq $PreviousSdkRoot) {
      Remove-Item Env:ANDROID_SDK_ROOT -ErrorAction SilentlyContinue
    } else {
      $env:ANDROID_SDK_ROOT = $PreviousSdkRoot
    }
    & subst.exe $SdkDrive /D | Out-Null
    & subst.exe $ProjectDrive /D | Out-Null
    $RestoredSdk = $Sdk.Replace('\', '\\').Replace(':', '\:')
    "sdk.dir=$RestoredSdk" | Set-Content -LiteralPath (Join-Path $PSScriptRoot "local.properties") -Encoding ASCII
  }
}
& $Python (Join-Path $ProjectRoot "packaging\build_java_tools.py")
if ($LASTEXITCODE -ne 0) { throw "Java işlem motorları derlenemedi." }
& $Python (Join-Path $ProjectRoot "packaging\sync_android.py")
if ($LASTEXITCODE -ne 0) { throw "Android kaynak eşitlemesi başarısız oldu." }
$EscapedSdk = $Sdk.Replace('\', '\\').Replace(':', '\:')
"sdk.dir=$EscapedSdk" | Set-Content -LiteralPath (Join-Path $PSScriptRoot "local.properties") -Encoding ASCII

$Gradle = Join-Path $PSScriptRoot "gradlew.bat"
if (-not (Test-Path -LiteralPath $Gradle)) {
  $GradleHome = $env:APK_CLEANER_GRADLE_HOME
  if (-not $GradleHome) {
    $GradleHome = Get-ChildItem "$env:LOCALAPPDATA\pnpm\store\v11\projects\*\work\android-toolchain\gradle\gradle-*" -Directory -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
  }
  if (-not $GradleHome) { throw "Gradle bulunamadı. APK_CLEANER_GRADLE_HOME değişkenini ayarla." }
  $Gradle = Join-Path $GradleHome "bin\gradle.bat"
}

Push-Location $PSScriptRoot
try {
  # Gradle 9'un Windows'ta kilitli problems-report.html dosyasına yeniden yazma
  # denemesi, başarılı paketlemeyi hatalı gösterebiliyor. Rapor yalnızca tanısal;
  # gerçek lint ve derleme görevleri çalışmaya devam eder.
  # Windows/JDK zipfs bazen sınıf yolu JAR'ını Gradle daemonunda kilitli
  # bırakabiliyor. Tek kullanımlık süreç bu kilidi ve sonraki derleme hatasını
  # önler; üretilen APK içeriğini etkilemez.
  $BuildArguments = @("clean", "assemble$Variant", "--no-daemon", "--max-workers=1", "--stacktrace", "--no-problems-report")
  if ($Offline) { $BuildArguments += "--offline" }
  & $Gradle @BuildArguments
  if ($LASTEXITCODE -ne 0) { throw "Android $Variant derlemesi başarısız oldu." }
} finally {
  Pop-Location
}

$Apk = Get-ChildItem (Join-Path $PSScriptRoot "app\build\outputs\apk\$($Variant.ToLowerInvariant())") -Filter "*.apk" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Apk) { throw "Üretilen APK bulunamadı." }
$OutputDir = Join-Path $ProjectRoot "outputs"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$Output = Join-Path $OutputDir $OutputName
Copy-Item -LiteralPath $Apk.FullName -Destination $Output -Force

# Android Gradle Plugin Release çıktısını zaten R8, kaynak küçültme ve APK
# optimizasyonundan geçirir. Son pakette bu garantileri ayrıca doğrula: standart
# ZIP hizalaması, 16 KB sayfa uyumlu yerel kütüphane hizalaması ve imza.
$BuildTools = Get-ChildItem (Join-Path $Sdk "build-tools") -Directory -ErrorAction Stop |
  Sort-Object Name -Descending | Select-Object -First 1
if (-not $BuildTools) { throw "Android build-tools bulunamadı." }
$ZipAlign = Join-Path $BuildTools.FullName "zipalign.exe"
$ApkSigner = Join-Path $BuildTools.FullName "apksigner.bat"
if (-not (Test-Path -LiteralPath $ZipAlign)) { throw "zipalign bulunamadı." }
if (-not (Test-Path -LiteralPath $ApkSigner)) { throw "apksigner bulunamadı." }

& $ZipAlign -c -P 16 4 $Output
if ($LASTEXITCODE -ne 0) { throw "APK ZIP/16 KB hizalama denetimi başarısız oldu." }
& $ApkSigner verify --verbose $Output
if ($LASTEXITCODE -ne 0) { throw "APK imza doğrulaması başarısız oldu." }

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Output).Hash
Write-Host "APK hazır: $Output"
Write-Host "SHA-256: $Hash"
