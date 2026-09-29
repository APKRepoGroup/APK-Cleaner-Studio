# APK Cleaner Studio v0.6.2

<p align="center">
  <img src="release-assets/APK-Cleaner-Studio-README-Kapagi.png" alt="APK Cleaner Studio promotional cover" width="100%">
</p>

[Türkçe README](README.md) · [Termux installation](README-TERMUX.md) · [Build from source](BUILDING.md) · [v0.6.2 release notes](RELEASE-NOTES-v0.6.2.md)

APK Cleaner Studio is a local Android package-processing tool that analyzes APK, APKS, APKM, and XAPK packages, removes verified advertising traces, and merges split packages into a single installable APK. The source package is never modified; every operation is performed on a new output file.

**Stable release:** v0.6.2 · **Engine:** 2.0 · **Platforms:** Android, Windows, and Termux

## Download

Download the current stable packages from [GitHub Releases](https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/latest):

| Platform | Package |
| --- | --- |
| Android | `APK-Cleaner-Studio-v0.6.2-Android.apk` |
| Windows | `APK-Cleaner-Studio-v0.6.2-Windows.exe` |
| Termux | `APK-Cleaner-Studio-v0.6.2-Termux.zip` |

You can verify each package against the `SHA256-v0.6.2.txt` file published with the same release. An illustrated overview of the changes is available on the [Telegraph release page](https://telegra.ph/APK-Cleaner-Studio-v062--Kararl%C4%B1-S%C3%BCr%C3%BCm-Notlar%C4%B1-09-20).

## What does it do?

- Inspects DEX, manifest, metadata, XML, asset, and native library traces for 18 built-in mobile advertising SDK families.
- Safely disables verified advertising calls according to the selected cleanup scope.
- Merges base, feature, and configuration split components from APKS, APKM, and XAPK packages into a single signed APK.
- Allows architecture, language, and DPI components to be selected in split packages.
- Presents Toast, Snackbar, DialogFragment, and PopupWindow calls that may have been added to the startup flow for review.
- On Android, lists installed apps with their icon, package name, and version, and allows the selected app to be shared or processed directly.
- Manages operation reports, output files, and previous operations from the same local interface.
- Supports light, dark, and system themes with responsive desktop and mobile layouts.

Files may be up to 1 GB. Analysis and modification take place on the device in use; packages are not uploaded to an external server.

## Workflow

1. Select an APK, APKS, APKM, or XAPK file. On Android, a package can also be obtained from the device through **Select from installed apps**.
2. The engine scans the package and reports advertising networks, DEX files, manifest entries, XML candidates, and split components.
3. Select the operation, cleanup scope, and optional improvements to apply.
4. The operation runs on a new file and produces the resulting APK, a detailed report, and an operation summary.

An operation can be cancelled while it is running. The original package is never modified.

## Operation types

### Remove ad traces

Modifies verified DEX calls, manifest entries, and XML ad views according to the selected profile. Normal ad patching does not decompile the DEX or produce Smali/Baksmali intermediate code; whenever possible, it replaces the target instruction bytes in place while preserving their length.

Ad cleanup is optional. If the analysis finds no verified advertising network, the profile cards are disabled while the independent improvements remain available.

### Create a single APK

Merges the split modules in an APKS, APKM, or XAPK package into a single installable APK. Architecture, language, and DPI components can be selected separately when the package supports them. Ad cleanup is independent of this operation and can be applied to the same output by enabling **Apply ad patch during conversion**.

## Cleanup scopes

- **Safe:** Disables only verified advertising load and display calls. This profile makes the fewest changes.
- **Balanced:** Extends the Safe profile by modifying manifest entries and verified XML ad views. This is the default and recommended option.
- **Advanced:** Extends the Balanced profile by targeting exact-match advertising assets and native SDK remnants.

In the Balanced and Advanced profiles, `res/layout*.xml` elements that contain a known advertising view are hidden with `0dp` and `gone`. Risky calls that return objects and could break the app if modified automatically are reported without being changed.

## Review startup messages

The engine inspects message calls reached through `onCreate`, `onResume`, and similar startup paths in Activity, Fragment, and Application classes. Candidates such as Toast, Snackbar, DialogFragment, and PopupWindow are listed together with their context.

No candidate is selected automatically. Only the startup call explicitly selected by the user is disabled while preserving the original instruction length; Activity bodies and shared `show()` methods are not removed wholesale. Because an APK alone cannot prove with certainty that a call was added later, the final decision is left to the user.

## Optional improvements

The following four options are independent of ad cleanup and of one another:

- **Remove DEX debug information:** Removes source-file, line, local-variable, and other debug entries. The affected DEX files are rewritten when this option is selected; Smali/Baksmali is not used.
- **Normalize the DEX structure:** Validates the standard DEX structure and rewrites it with DexLib2. It does not recover original class or method names without a mapping file. If the engine cannot read the DEX structure safely, it stops the operation instead of producing a damaged output.
- **Optimize the patched APK:** Applies standard ZIP alignment before signing. It does not rebuild DEX, manifest, or RES content; it only arranges the ZIP layout of files inside the APK.
- **Remove RES resource protection:** Runs APKEditor’s plain `x` operation (`java -jar APKEditor.jar x -i input.apk -o output.apk`) directly. The `-fix-types` option is not used, and the package produced by APKEditor is passed unchanged to the next stage.

Split package conversion also presents the **Apply ad patch during conversion** option. When **Create a single APK** completes, this option applies the selected Safe, Balanced, or Advanced scope to the same output.

## Android

The Android package uses the `com.apkrepo.apkcleanerstudio` application ID and version code `62`. The minimum supported Android version is Android 8.0 (API 26). The v0.6.2 package can be installed as an update over v0.6.1 when it uses the same application ID.

Android-specific features:

- Search and select installed apps by name, icon, package ID, and version.
- Prepare the selected app’s base APK together with any split components.
- Export the source package through the Android share sheet.
- Download or share the generated APK, or send it directly to the system package installer.
- Check the Android version, CPU architecture, existing installation, and possible signature conflicts before installation.
- Reopen the interface without closing the app if WebView exits unexpectedly.

## Windows

Run `APK-Cleaner-Studio-v0.6.2-Windows.exe`; no separate Python installation or BAT file is required. If Java or another required processing component is missing, the **Prepare missing components** button in the interface installs the verified portable toolchain in the user directory.

The application listens on the local network by default. The console displays `127.0.0.1` for this computer and a local network address for other devices on the same trusted network. LAN access does not include authentication and should be used only on trusted private networks.

The local Windows interface can optionally run over HTTPS. When the local certificate is trusted, the `127.0.0.1` connection is upgraded to HTTPS, while the certificate’s private key remains on the device. To use HTTPS from a phone, download the CA certificate from **Local processing engine → Mobile HTTPS certificate** in the interface. If you do not want to install the certificate, you can continue using the local HTTP connection.

## Termux

Extract the ZIP package and open its directory in Termux. If the package is in Android’s Downloads folder, for example:

```bash
termux-setup-storage
cd ~/storage/downloads/APK-Cleaner-Studio-v0.6.2-Termux
```

Run once for the initial installation:

```bash
bash install-termux.sh
```

For later sessions:

```bash
bash start-termux.sh
```

The installer uses OpenJDK 25 when it is available in the Termux repository. If that package is not provided for the device architecture or configured repository, it continues with OpenJDK 21. When Termux:Widget is installed, a home-screen shortcut is also prepared. See [README-TERMUX.md](README-TERMUX.md) for detailed installation instructions.

## Reports, history, and local data

- The result screen displays **Open report**, **Share**, **Install APK**, and **Download APK** where supported by the platform.
- Before an output is offered, the app verifies APK archive CRC integrity, manifest and DEX entries, native libraries, and its signature. Selected split modules are checked before merging.
- The operation report shows before/after size and SHA-256 for changed DEX files, removed manifest entries, and previous/new XML field values.
- Frequently used processing options can be saved as local presets. These store no source APK, filename, or user data; they remain in that device's browser storage.
- Completed operations can be reopened; their reports and outputs can be viewed or downloaded when available.
- Source packages, reports, and outputs are retained for 14 days on the local device only. Unwanted entries can be removed from the history list.
- Local network sessions refresh every 10 seconds, and disconnected devices are removed from the list after 5 minutes. A custom display name is stored only on the device running the application.

## Limitations and safety

- Automatic ad cleanup cannot be guaranteed to work without issues on every APK.
- A re-signed APK may not install over a store build or an existing installation signed with a different key.
- Universal APK generation depends on the source app’s split assumptions for some optional feature modules.
- The application is not designed to bypass paid features, purchases, subscriptions, or license checks.
- Use it only with packages you own or are authorized to modify and test.

## License

APK Cleaner Studio is released as open-source software under the GNU General Public License v3.0 with the notice `Copyright (C) 2026 APK Repo Grubu`. You may use, inspect, modify, and redistribute the application in accordance with the license terms. See [LICENSE](LICENSE) for the complete text.

Third-party components retain their respective licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for details.

See [BUILDING.md](BUILDING.md) for source-build, local signing-key generation, and packaging instructions.
