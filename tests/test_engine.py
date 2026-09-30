import sys
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))

from engine import (
    ANDROID_NS,
    _ACTIVE_TOOLS,
    _ACTIVE_TOOLS_LOCK,
    Toolchain,
    _process_one_dex,
    _temporary_directory,
    _android_archive_package,
    deep_removals,
    inspect_apk,
    inspect_split_package,
    inspect_split_components,
    _selected_split_modules,
    patch_ad_layouts,
    patch_manifest_binary,
    rewrite_apk,
    run_checked,
    sign_apk,
    terminate_active_tools,
    validate_clone_package_name,
    validate_package_archive,
    verify_output_apk,
)


class EngineTests(unittest.TestCase):
    def test_android_archive_package_fallback_validates_native_result(self):
        class FakeRunner:
            @staticmethod
            def inspectArchivePackage(_path):
                return "com.example.split"

        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch.dict(
            sys.modules, {"java": types.SimpleNamespace(jclass=lambda _name: FakeRunner)}
        ):
            self.assertEqual(_android_archive_package(Path("base.apk")), "com.example.split")
        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch.dict(
            sys.modules, {"java": types.SimpleNamespace(jclass=lambda _name: types.SimpleNamespace(
                inspectArchivePackage=lambda _path: "invalid package"
            ))}
        ):
            self.assertEqual(_android_archive_package(Path("base.apk")), "")

    def test_android_split_analysis_uses_archive_package_when_axml_inspection_fails(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "base.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("classes.dex", b"dex\n035\x00")
                archive.writestr("AndroidManifest.xml", b"binary-manifest")
            with mock.patch("engine.inspect_manifest_package", return_value=""), mock.patch(
                "engine._android_archive_package", return_value="com.example.split"
            ):
                report = inspect_apk(source)
            self.assertEqual(report["package_name"], "com.example.split")
            self.assertEqual(report["suggested_clone_package_name"], "com.example.split.clone")

    def test_embedded_tool_failure_names_the_tool_and_keeps_diagnostics(self):
        class FailingRunner:
            @staticmethod
            def run(_command, _cwd):
                return types.SimpleNamespace(exitCode=1, output="Error: XML kaynakları okunamadı\n")

        log = []
        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), \
                mock.patch.dict(sys.modules, {"java": types.SimpleNamespace(jclass=lambda _name: FailingRunner)}):
            with self.assertRaisesRegex(RuntimeError, "APKEditor d başarısız oldu \\(1\\): Error: XML kaynakları okunamadı"):
                run_checked(["embedded-java", "-jar", "APKEditor.jar", "d", "-i", "sample.apk"], log)
        self.assertIn("Error: XML kaynakları okunamadı", log)

        class PlainFailure:
            @staticmethod
            def run(_command, _cwd):
                return types.SimpleNamespace(exitCode=1, output="Kaynak tablosu okunamadı\n")

        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), \
                mock.patch.dict(sys.modules, {"java": types.SimpleNamespace(jclass=lambda _name: PlainFailure)}):
            with self.assertRaisesRegex(RuntimeError, "APKEditor m başarısız oldu \\(1\\): Kaynak tablosu okunamadı"):
                run_checked(["embedded-java", "-jar", "APKEditor.jar", "m", "-i", "sample.apks"], [])

    def test_archive_validation_rejects_traversal_duplicate_and_decompression_bombs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            traversal = root / "traversal.apk"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("../outside", b"x")
            with self.assertRaisesRegex(ValueError, "arşiv yolu"):
                validate_package_archive(traversal)

            duplicate = root / "duplicate.apk"
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("classes.dex", b"one")
                archive.writestr("classes.dex", b"two")
            with self.assertRaisesRegex(ValueError, "birden fazla"):
                validate_package_archive(duplicate)

            bomb = root / "bomb.apk"
            with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                archive.writestr("classes.dex", b"0" * (2 * 1024 * 1024))
            with self.assertRaisesRegex(ValueError, "sıkıştırma oranı"):
                validate_package_archive(bomb)

    def test_output_verification_rejects_missing_native_library(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, output = root / "source.apk", root / "output.apk"
            entries = {"AndroidManifest.xml": b"manifest", "classes.dex": b"dex", "lib/arm64-v8a/libsample.so": b"native"}
            with zipfile.ZipFile(source, "w") as archive:
                for entry, payload in entries.items():
                    archive.writestr(entry, payload)
            with zipfile.ZipFile(output, "w") as archive:
                for entry, payload in entries.items():
                    if not entry.startswith("lib/"):
                        archive.writestr(entry, payload)
            with self.assertRaisesRegex(RuntimeError, "native kütüphanesi eksik"):
                verify_output_apk(source, output, mock.Mock(), [])

    def test_deep_removal_plan_only_exempts_intentionally_removed_native_entries(self):
        with tempfile.TemporaryDirectory() as name, mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "0"}):
            root = Path(name)
            source = root / "source.apk"
            ad_library = "lib/arm64-v8a/libfixtureads.so"
            core_library = "lib/arm64-v8a/libcore.so"
            with zipfile.ZipFile(source, "w") as archive:
                for entry, data in {
                    "AndroidManifest.xml": b"manifest", "classes.dex": b"dex",
                    ad_library: b"ads", core_library: b"core",
                }.items():
                    archive.writestr(entry, data)
            with mock.patch("engine.load_profiles", return_value={
                "fixture": {"assets": [], "libraries": ["libfixtureads.so"]},
            }):
                planned = deep_removals(source, {"fixture"})
            self.assertEqual(planned, {ad_library})
            tools = types.SimpleNamespace(apksigner="fixture-apksigner")
            cases = (
                ("balanced", set(), set(), None, 2),
                ("deep", planned, planned, None, 1),
                ("unplanned_native_loss", planned | {core_library}, planned, "native kütüphanesi eksik", None),
                ("ad_library_not_removed", set(), planned, "kaldırılması istenen dosya", None),
                ("dex_removal_not_exempt", planned | {"classes.dex"}, planned | {"classes.dex"}, "DEX bileşeni eksik", None),
            )
            for label, actual_removals, removal_plan, error, native_count in cases:
                with self.subTest(case=label), mock.patch("engine.run_checked") as signature_check:
                    output = root / f"{label}.apk"
                    rewrite_apk(source, output, {}, actual_removals)
                    if error:
                        with self.assertRaisesRegex(RuntimeError, error):
                            verify_output_apk(source, output, tools, [], removed_files=removal_plan)
                        signature_check.assert_not_called()
                    else:
                        result = verify_output_apk(source, output, tools, [], removed_files=removal_plan)
                        self.assertTrue(result["passed"])
                        self.assertEqual(result["native_library_count"], native_count)
                        signature_check.assert_called_once_with(
                            ["fixture-apksigner", "verify", "--verbose", str(output)], [],
                        )

    def test_planned_native_removal_does_not_bypass_signature_verification(self):
        with tempfile.TemporaryDirectory() as name, mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "0"}):
            source, output = Path(name) / "source.apk", Path(name) / "output.apk"
            removed = {"lib/arm64-v8a/libfixtureads.so"}
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"manifest")
                archive.writestr("classes.dex", b"dex")
                archive.writestr(next(iter(removed)), b"ads")
            rewrite_apk(source, output, {}, removed)
            with mock.patch("engine.run_checked", side_effect=RuntimeError("fixture signature rejected")):
                with self.assertRaisesRegex(RuntimeError, "fixture signature rejected"):
                    verify_output_apk(source, output, types.SimpleNamespace(apksigner="fixture-apksigner"), [], removed_files=removed)

    def test_clone_name_must_differ_and_keep_valid_package_shape(self):
        self.assertEqual(validate_clone_package_name("com.example.app", "com.example.app.clone"), "com.example.app.clone")
        with self.assertRaisesRegex(ValueError, "farklı olmalı"):
            validate_clone_package_name("com.example.app", "com.example.app")
        with self.assertRaisesRegex(ValueError, "geçerli bölüm"):
            validate_clone_package_name("com.example.app", "bad name")

    def test_android_signer_failure_surfaces_the_real_error_without_fake_unsigned_output(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            unsigned = root / "input.apk"
            unsigned.write_bytes(b"apk")

            class BrokenRunner:
                @staticmethod
                def signApk(_input, _output, _optimize):
                    raise RuntimeError("test imza arızası")

            java_module = types.SimpleNamespace(jclass=lambda _name: BrokenRunner)
            with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}, clear=False), \
                    mock.patch.dict(sys.modules, {"java": java_module}):
                with self.assertRaisesRegex(RuntimeError, "test imza arızası"):
                    sign_apk(unsigned, root / "output.apk", mock.Mock(), [])
            self.assertFalse((root / "output.unsigned.apk").exists())

    def test_android_temp_directory_is_recreated_if_removed(self):
        with tempfile.TemporaryDirectory() as parent_name:
            temp_root = Path(parent_name) / "private-runtime" / "tmp"
            original_tempdir = tempfile.tempdir
            try:
                with mock.patch.dict(os.environ, {
                    "APK_CLEANER_ANDROID": "1",
                    "APK_CLEANER_TEMP_ROOT": str(temp_root),
                }, clear=False):
                    with _temporary_directory("apkcleaner-test-") as first:
                        self.assertEqual(Path(first).parent, temp_root)
                    shutil.rmtree(temp_root)
                    with _temporary_directory("apkcleaner-test-") as second:
                        self.assertEqual(Path(second).parent, temp_root)
                        self.assertTrue(Path(second).is_dir())
                    self.assertEqual(os.environ["TMPDIR"], str(temp_root))
            finally:
                tempfile.tempdir = original_tempdir

    def test_split_preanalysis_scans_inner_apk_without_merging(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            inner_buffer = io.BytesIO()
            with zipfile.ZipFile(inner_buffer, "w") as inner:
                inner.writestr("classes.dex", b"dex\ncom/google/android/gms/ads/AdView")
                inner.writestr("AndroidManifest.xml", b"com.google.android.gms.ads.AdActivity")
            package = root / "sample.apks"
            with zipfile.ZipFile(package, "w") as outer:
                outer.writestr("base.apk", inner_buffer.getvalue())
                outer.writestr("split_config.arm64_v8a.apk", b"native-placeholder")
            inventory = inspect_split_components(package)
            with mock.patch("engine.run_checked") as run:
                result = inspect_split_package(package, inventory, known_sha256="upload-hash")
            self.assertTrue(all("--inspect-package" in call.args[0] for call in run.call_args_list))
            self.assertTrue(result["fast_split_scan"])
            self.assertEqual(result["sha256"], "upload-hash")
            self.assertEqual(result["network_count"], 1)

    def test_standalone_base_apk_reports_required_split_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "base.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("classes.dex", b"dex\n")
                archive.writestr(
                    "AndroidManifest.xml",
                    "com.android.vending.splits.required".encode("utf-16le"),
                )
            report = inspect_apk(source)
            self.assertTrue(report["requires_splits"])

    def test_precomputed_analysis_skips_duplicate_archive_inspection(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"manifest")
                archive.writestr("classes.dex", b"dex fixture")
            report = {
                "filename": "source.apk", "size": 7, "sha256": "source-hash",
                "dex": [], "dex_count": 0, "detections": [], "network_count": 0,
                "manifest_hits": {}, "layout_hits": [], "install_source_checks": [],
                "suspicious_files": [], "toolchain": {}, "warnings": [], "requires_splits": True,
            }
            tools = mock.Mock()
            tools.status.return_value = {"clean_ready": True, "resource_tool": True, "manifest_tool": True, "signer": True}
            tools.zipalign = "zipalign"
            def fake_sign(_unsigned, output, _tools, _log, optimize=False):
                shutil.copyfile(_unsigned, output)
                return True, None

            with mock.patch("engine.inspect_apk") as inspect, mock.patch(
                "engine.Toolchain.detect", return_value=tools
            ), mock.patch("engine.sign_apk", side_effect=fake_sign), mock.patch(
                "engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}
            ), mock.patch(
                "engine.sha256", return_value="output-hash"
            ):
                result = __import__("engine").process_apk(
                    source, root / "output", patch_ads=False, analysis_report=report, source_size_bytes=1234
                )
            inspect.assert_not_called()
            self.assertTrue(result["analysis_reused"])
            self.assertEqual(result["source_size_bytes"], 1234)
            self.assertEqual(result["output_size_bytes"], (root / "output" / result["output"]).stat().st_size)
            self.assertIsNone(result["cleaning_profile_applied"])

    def test_message_only_processing_is_reported_as_patch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"manifest")
                archive.writestr("classes.dex", b"dex fixture")
            report = {
                "filename": "source.apk", "size": source.stat().st_size, "sha256": "source-hash",
                "dex": [{"name": "classes.dex", "networks": []}], "dex_count": 1,
                "detections": [], "network_count": 0, "manifest_hits": {}, "layout_hits": [],
                "install_source_checks": [], "suspicious_files": [], "toolchain": {}, "warnings": [],
            }
            tools = mock.Mock()
            tools.status.return_value = {"clean_ready": True, "resource_tool": True, "manifest_tool": True, "signer": True}
            tools.zipalign = "zipalign"

            def fake_dex(name, _dex_in, temp, *_args, **_kwargs):
                patched = temp / "patched-classes.dex"
                patched.write_bytes(b"patched dex")
                return name, patched, {
                    "changed_files": 1, "void_patches": 0, "boolean_patches": 0,
                    "callback_patches": 0, "message_patches": 1,
                    "debug_directives_removed": 0, "clone_strings_changed": 0, "risky_calls": [],
                }, ["RESULT message_patches=1"]

            def fake_sign(_unsigned, output, _tools, _log, optimize=False):
                shutil.copyfile(_unsigned, output)
                return True, None

            with mock.patch("engine.Toolchain.detect", return_value=tools), mock.patch(
                "engine._process_one_dex", side_effect=fake_dex
            ), mock.patch("engine.sign_apk", side_effect=fake_sign), mock.patch(
                "engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}
            ), mock.patch(
                "engine.sha256", return_value="output-hash"
            ), mock.patch("engine.inspect_startup_calls", return_value=[{
                "id": "classes.dex:lc-target", "dex": "classes.dex", "owner_class": "Ltest/MainActivity;",
                "owner_method": "onCreate", "target_class": "Ltest/DialogHelper;", "target_method": "start",
            }]):
                result = __import__("engine").process_apk(
                    source, root / "output", patch_ads=False,
                    analysis_report=report, message_targets=["classes.dex:lc-target"],
                )
            self.assertEqual(result["operation"], "patch")
            self.assertEqual(result["patches"]["message_patches"], 1)

    def test_split_inventory_and_automatic_density_selection(self):
        with tempfile.TemporaryDirectory() as name:
            package = Path(name) / "sample.apks"
            with zipfile.ZipFile(package, "w") as archive:
                for entry in (
                    "base.apk",
                    "split_config.arm64_v8a.apk",
                    "split_config.armeabi_v7a.apk",
                    "split_config.x86.apk",
                    "split_config.xhdpi.apk",
                    "split_config.xxhdpi.apk",
                    "split_config.en.apk",
                    "split_config.tr.apk",
                    "split_config.de.apk",
                ):
                    archive.writestr(entry, b"apk")
            inventory = inspect_split_components(package)
            self.assertEqual(inventory["abis"], ["armeabi-v7a", "arm64-v8a", "x86"])
            self.assertEqual(inventory["recommended_densities"]["arm64-v8a"], "xxhdpi")
            selected = _selected_split_modules(inventory, {"abis": ["arm64-v8a"], "languages": ["tr"]})
            self.assertIn("base.apk", selected)
            self.assertIn("split_config.arm64_v8a.apk", selected)
            self.assertIn("split_config.xxhdpi.apk", selected)
            self.assertIn("split_config.tr.apk", selected)
            self.assertNotIn("split_config.xhdpi.apk", selected)
            self.assertNotIn("split_config.en.apk", selected)
            self.assertNotIn("split_config.de.apk", selected)

    def test_optional_apk_optimization_controls_zipalign(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            unsigned = root / "unsigned.apk"
            unsigned.write_bytes(b"apk")
            tools = Toolchain(
                java="java",
                keytool=None,
                dexlib2=None,
                direct_patcher=None,
                binary_manifest_patcher=None,
                apkeditor=None,
                uber_signer=Path("uber-apk-signer.jar"),
                zipalign="zipalign",
                apksigner=None,
            )
            commands: list[list[str]] = []

            def fake_run(command, log, cwd=None):
                commands.append(command)
                signer_output = Path(command[command.index("--out") + 1])
                signer_output.mkdir(parents=True, exist_ok=True)
                (signer_output / "signed.apk").write_bytes(b"signed")

            with mock.patch("engine.run_checked", side_effect=fake_run):
                signed, _ = sign_apk(unsigned, root / "optimized.apk", tools, [], optimize=True)
            self.assertTrue(signed)
            self.assertNotIn("--skipZipAlign", commands[0])
            self.assertIn("--zipAlignPath", commands[0])

            commands.clear()
            with mock.patch("engine.run_checked", side_effect=fake_run):
                signed, _ = sign_apk(unsigned, root / "standard.apk", tools, [], optimize=False)
            self.assertTrue(signed)
            self.assertIn("--skipZipAlign", commands[0])

    def test_resource_normalization_request_never_rewrites_resource_table(self):
        source = Path("source.apk")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"manifest")
                archive.writestr("resources.arsc", b"resource-table")
                archive.writestr("classes.dex", b"dex\n035\x00")

            def fake_sign(_unsigned, output, _tools, _log, optimize=False):
                shutil.copyfile(_unsigned, output)
                return True, None

            with mock.patch("engine.Toolchain.detect") as detect, mock.patch(
                "engine.sign_apk", side_effect=fake_sign
            ), mock.patch("engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}), mock.patch(
                "engine.inspect_manifest_package", return_value=""
            ), mock.patch("engine.sha256", return_value="hash"):
                detect.return_value.status.return_value = {
                    "clean_ready": True, "manifest_tool": True, "signer": True
                }
                result = __import__("engine").process_apk(
                    source, root / "output", patch_ads=False, normalize_resources=True
                )

            self.assertFalse(result["resources"]["applied"])
            self.assertTrue(result["resources"]["skipped"])
            self.assertFalse(any("-fix-types" in line for line in result["log"]))

    def test_res_deobfuscation_uses_apkeditor_output_without_manifest_restore(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"original-manifest")
                archive.writestr("resources.arsc", b"original-resources")
                archive.writestr("res/layout/main.xml", b"original-layout")
                archive.writestr("classes.dex", b"dex\n035\x00")

            tools = Toolchain(
                java="java",
                keytool=None,
                dexlib2=None,
                direct_patcher=None,
                binary_manifest_patcher=None,
                apkeditor=Path("APKEditor.jar"),
                uber_signer=Path("uber-apk-signer.jar"),
                zipalign=None,
                apksigner=None,
            )
            signed_input: dict[str, bytes] = {}

            commands: list[list[str]] = []

            def fake_run(command, log, cwd=None):
                commands.append(command)
                action = command[3]
                self.assertNotIn("-fix-types", command)
                output = Path(command[command.index("-o") + 1])
                self.assertEqual(action, "x")
                self.assertNotIn("-public-xml", command)
                with zipfile.ZipFile(output, "w") as archive:
                    archive.writestr("AndroidManifest.xml", b"apkeditor-manifest")
                    archive.writestr("resources.arsc", b"apkeditor-resources")
                    archive.writestr("res/layout/main.xml", b"apkeditor-layout")
                    archive.writestr("classes.dex", b"dex\n035\x00")

            def fake_sign(unsigned, output, _tools, log, optimize=False):
                with zipfile.ZipFile(unsigned) as archive:
                    signed_input["manifest"] = archive.read("AndroidManifest.xml")
                    signed_input["resources"] = archive.read("resources.arsc")
                    signed_input["layout"] = archive.read("res/layout/main.xml")
                shutil.copyfile(unsigned, output)
                return True, None

            with mock.patch("engine.Toolchain.detect", return_value=tools), mock.patch(
                "engine.run_checked", side_effect=fake_run
            ), mock.patch("engine.sign_apk", side_effect=fake_sign), mock.patch(
                "engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}
            ), mock.patch(
                "engine.sha256", return_value="hash"
            ):
                result = __import__("engine").process_apk(
                    source,
                    root / "output",
                    patch_ads=False,
                    deobfuscate_resources=True,
                )

            self.assertEqual(signed_input["manifest"], b"apkeditor-manifest")
            self.assertEqual(signed_input["resources"], b"apkeditor-resources")
            self.assertEqual(signed_input["layout"], b"apkeditor-layout")
            self.assertTrue(result["resources"]["applied"])
            self.assertTrue(result["resources"]["resource_names_preserved"])
            self.assertEqual([command[3] for command in commands], ["x"])
            self.assertEqual(result["resources"]["engine"], "APKEditor x")
            self.assertNotIn("manifest_restored", result["resources"])

    def test_layout_check_does_not_require_fast_scan_hit(self):
        source = __import__("inspect").getsource(__import__("engine").process_apk)
        self.assertNotIn('report["layout_hits"] and tools.apkeditor', source)
        self.assertLess(source.index("if deobfuscate_resources:"), source.index("if should_patch_layouts:"))

    def test_run_checked_preserves_result_line_before_long_report(self):
        log: list[str] = []
        script = "print('RESULT changed_files=1'); [print(f'RISKY\\t{i}') for i in range(120)]"
        run_checked([sys.executable, "-c", script], log)
        self.assertIn("RESULT changed_files=1", log)
        self.assertLessEqual(len(log), 82)

    def test_run_checked_terminates_a_timed_out_tool(self):
        log: list[str] = []
        with self.assertRaisesRegex(RuntimeError, "zaman aşımına uğradı"):
            run_checked([sys.executable, "-c", "import time; time.sleep(5)"], log, timeout=1)
        with _ACTIVE_TOOLS_LOCK:
            self.assertFalse(_ACTIVE_TOOLS)

    def test_active_dex_path_uses_direct_patcher_without_baksmali(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            dex_in = root / "classes.dex"
            dex_in.write_bytes(b"dex fixture")
            tools = Toolchain(
                java="java",
                keytool=None,
                dexlib2=Path("dexlib2-runtime.jar"),
                direct_patcher=Path("direct-dex-patcher.jar"),
                binary_manifest_patcher=Path("binary-xml-patcher.jar"),
                apkeditor=None,
                uber_signer=None,
                zipalign=None,
                apksigner=None,
            )

            def fake_run(command, log, cwd=None):
                self.assertIn("local.apkcleaner.dex.DirectDexPatcher", command)
                self.assertFalse(any("baksmali" in str(item).lower() for item in command))
                self.assertIn("--normalize-dex", command)
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"patched dex")
                log.append("RESULT changed_files=1 void_patches=2 boolean_patches=0 debug_directives_removed=0")

            with mock.patch("engine.run_checked", side_effect=fake_run):
                _, dex_out, result, _ = _process_one_dex(
                    "classes.dex", dex_in, root, tools, {"google_ads"}, "balanced", False
                )
            self.assertEqual(dex_out.read_bytes(), b"patched dex")
            self.assertEqual(result["void_patches"], 2)

    def test_direct_patcher_blocks_native_banner_rendering_in_deep_mode(self):
        java = shutil.which("java")
        apkeditor = ROOT / "studio" / "tools" / "APKEditor.jar"
        patcher = ROOT / "studio" / "tools" / "direct-dex-patcher.jar"
        dexlib = ROOT / "studio" / "tools" / "dexlib2-runtime.jar"
        if not java or not all(path.is_file() for path in (apkeditor, patcher, dexlib)):
            self.skipTest("Yerel Java/DEX test araçları bulunamadı.")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            smali = root / "smali" / "local" / "BannerFixture.smali"
            smali.parent.mkdir(parents=True)
            smali.write_text(
                ".class public Llocal/BannerFixture;\n"
                ".super Ljava/lang/Object;\n\n"
                ".method public static render(Lcom/google/android/gms/ads/nativead/NativeAdView;Lcom/google/android/gms/ads/nativead/NativeAd;)V\n"
                "    .registers 2\n"
                "    invoke-virtual {p0, p1}, Lcom/google/android/gms/ads/nativead/NativeAdView;->setNativeAd(Lcom/google/android/gms/ads/nativead/NativeAd;)V\n"
                "    invoke-virtual {p0}, Lcom/google/android/gms/ads/nativead/NativeAdView;->a()V\n"
                "    return-void\n"
                ".end method\n\n"
                ".method public onNativeAdLoaded(Lcom/google/android/gms/ads/nativead/NativeAd;)V\n"
                "    .registers 2\n"
                "    invoke-static {}, Ljava/lang/System;->gc()V\n"
                "    return-void\n"
                ".end method\n",
                encoding="utf-8",
            )
            dex_in = root / "classes.dex"
            assembled = subprocess.run(
                [java, "-cp", str(apkeditor), "org.jf.smali.Main", "assemble", str(root / "smali"), "-o", str(dex_in)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(assembled.returncode, 0, assembled.stderr)
            tools = Toolchain(
                java=java,
                keytool=None,
                dexlib2=dexlib,
                direct_patcher=patcher,
                binary_manifest_patcher=None,
                apkeditor=apkeditor,
                uber_signer=None,
                zipalign=None,
                apksigner=None,
            )
            _, dex_out, result, _ = _process_one_dex(
                "classes.dex", dex_in, root, tools, {"google_ads"}, "deep", False
            )
            self.assertTrue(dex_out.is_file())
            self.assertEqual(result["void_patches"], 2)
            self.assertEqual(result["callback_patches"], 1)
            disassembled = root / "patched-smali"
            decoded = subprocess.run(
                [java, "-cp", str(apkeditor), "org.jf.baksmali.Main", "disassemble", str(dex_out), "-o", str(disassembled)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            patched_smali = (disassembled / "local" / "BannerFixture.smali").read_text(encoding="utf-8")
            render_body = patched_smali.split(".method public static render", 1)[1].split(".end method", 1)[0]
            callback_body = patched_smali.split(".method public onNativeAdLoaded", 1)[1].split(".end method", 1)[0]
            self.assertEqual(render_body.count("goto/32"), 2)
            self.assertNotIn("invoke-virtual", render_body)
            self.assertNotIn("Ljava/lang/System;->gc", callback_body)
            self.assertLessEqual(callback_body.count("\n    nop"), 2)

    def test_binary_manifest_path_never_invokes_text_decoder(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "manifest.bin"
            output = root / "patched.bin"
            source.write_bytes(b"binary manifest fixture")
            tools = Toolchain(
                java="java",
                keytool=None,
                dexlib2=None,
                direct_patcher=None,
                binary_manifest_patcher=Path("binary-xml-patcher.jar"),
                apkeditor=Path("APKEditor.jar"),
                uber_signer=None,
                zipalign=None,
                apksigner=None,
            )

            def fake_run(command, log, cwd=None):
                self.assertIn("local.apkcleaner.xml.BinaryManifestPatcher", command)
                self.assertNotIn(" d ", " ".join(str(item) for item in command))
                output.write_bytes(source.read_bytes())
                log.extend(("REFERENCES preserved=3", "RESULT removed=0"))

            with mock.patch("engine.run_checked", side_effect=fake_run):
                result = patch_manifest_binary(source, output, tools, {"google_ads"}, [])
            self.assertTrue(result["references_preserved"])
            self.assertEqual(result["engine"], "binary-axml")

    def test_known_sdk_layout_is_hidden(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            layout = root / "resources" / "package_1" / "res" / "layout" / "main.xml"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                f'<LinearLayout xmlns:android="{ANDROID_NS}">'
                '<com.google.android.gms.ads.AdView android:layout_width="match_parent" android:layout_height="wrap_content" />'
                '</LinearLayout>',
                encoding="utf-8",
            )
            result = patch_ad_layouts(root, {"google_ads"})
            output = layout.read_text(encoding="utf-8")
            self.assertEqual(result["count"], 1)
            self.assertIn('android:layout_width="0dp"', output)
            self.assertIn('android:layout_height="0dp"', output)
            self.assertIn('android:visibility="gone"', output)
            self.assertEqual(result["archive_entries"], ["res/layout/main.xml"])

    def test_deep_profile_hides_dynamic_native_ad_container(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            layout = root / "resources" / "package_1" / "res" / "layout" / "feed.xml"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                f'<androidx.constraintlayout.widget.ConstraintLayout xmlns:android="{ANDROID_NS}">'
                '<FrameLayout android:id="@+id/native_ad_container" '
                'android:layout_width="match_parent" android:layout_height="wrap_content" />'
                '</androidx.constraintlayout.widget.ConstraintLayout>',
                encoding="utf-8",
            )
            result = patch_ad_layouts(root, {"google_ads"}, "deep")
            output = layout.read_text(encoding="utf-8")
            self.assertEqual(result["count"], 1)
            self.assertIn("@id/native_ad_container", result["hidden"][0])
            self.assertIn('android:layout_width="0dp"', output)
            self.assertIn('android:layout_height="0dp"', output)
            self.assertIn('android:visibility="gone"', output)

    def test_balanced_profile_does_not_hide_generic_container_by_id(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            layout = root / "resources" / "package_1" / "res" / "layout" / "feed.xml"
            layout.parent.mkdir(parents=True)
            original = (
                f'<FrameLayout xmlns:android="{ANDROID_NS}" android:id="@+id/native_ad_container" '
                'android:layout_width="match_parent" android:layout_height="wrap_content" />'
            )
            layout.write_text(original, encoding="utf-8")
            result = patch_ad_layouts(root, {"google_ads"}, "balanced")
            self.assertEqual(result["count"], 0)
            self.assertNotIn("visibility", layout.read_text(encoding="utf-8"))

    def test_deep_profile_does_not_hide_non_ad_banner_identifier(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            layout = root / "resources" / "package_1" / "res" / "layout" / "home.xml"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                f'<ImageView xmlns:android="{ANDROID_NS}" android:id="@+id/home_promo_banner" '
                'android:layout_width="match_parent" android:layout_height="wrap_content" />',
                encoding="utf-8",
            )
            result = patch_ad_layouts(root, {"google_ads"}, "deep")
            self.assertEqual(result["count"], 0)

    def test_selective_archive_rewrite_preserves_resource_table(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.apk"
            replacement = root / "manifest.bin"
            destination = root / "patched.apk"
            replacement.write_bytes(b"patched-manifest")
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"original-manifest")
                archive.writestr("resources.arsc", b"original-resource-table")
                archive.writestr("classes.dex", b"original-dex")
            rewrite_apk(source, destination, {"AndroidManifest.xml": replacement}, set())
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.read("AndroidManifest.xml"), b"patched-manifest")
                self.assertEqual(archive.read("resources.arsc"), b"original-resource-table")
                self.assertEqual(archive.read("classes.dex"), b"original-dex")

    def test_apk_inspection_reports_manifest_and_layout_candidates(self):
        with tempfile.TemporaryDirectory() as name:
            apk = Path(name) / "sample.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(
                    "classes.dex",
                    b"dex\ncom/google/android/gms/ads/AdView\ncom/google/android/play/core/integrity\n"
                    b"initializeLicenseCheck\nLandroid/widget/Toast;\nmakeText\n"
                    b"Landroidx/appcompat/app/AlertDialog$Builder;",
                )
                archive.writestr("AndroidManifest.xml", b"com.google.android.gms.ads.AdActivity")
                archive.writestr("res/layout/main.xml", b"com.google.android.gms.ads.AdView")
            result = inspect_apk(apk)
            self.assertEqual(result["network_count"], 1)
            self.assertTrue(result["manifest_hits"])
            self.assertEqual(len(result["layout_hits"]), 1)
            self.assertIn("Play Integrity API", result["install_source_checks"])
            self.assertIn("Lisans / dağıtım doğrulaması", result["install_source_checks"])
            self.assertTrue(result["source_integrity_risk"])
            self.assertGreaterEqual(result["message_ui_candidate_count"], 3)
            self.assertEqual(
                {item["label"] for item in result["message_ui_candidates"]},
                {"Toast mesajı", "Diyalog penceresi"},
            )

    def test_shutdown_terminates_active_tool_processes(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        with _ACTIVE_TOOLS_LOCK:
            _ACTIVE_TOOLS.add(process)
        try:
            terminate_active_tools()
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.kill()
            with _ACTIVE_TOOLS_LOCK:
                _ACTIVE_TOOLS.discard(process)


if __name__ == "__main__":
    unittest.main()
