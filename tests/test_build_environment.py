import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AndroidBuildEnvironmentTests(unittest.TestCase):
    def test_short_path_build_restores_the_physical_java_environment_before_unmapping(self):
        source = (ROOT / "android/build-android.ps1").read_text(encoding="utf-8")
        block = source.split('$PreviousSdkRoot = $env:ANDROID_SDK_ROOT', 1)[1].split('& $Python (Join-Path', 1)[0]
        self.assertIn('$PreviousJavaHome = $env:JAVA_HOME', block)
        self.assertIn('$PreviousPath = $env:Path', block)
        cleanup = block.split('} finally {', 1)[1]
        unmap = cleanup.index('& subst.exe $SdkDrive /D')
        self.assertLess(cleanup.index('$env:JAVA_HOME = $PreviousJavaHome'), unmap)
        self.assertLess(cleanup.index('$env:Path = $PreviousPath'), unmap)
