"""Synthetic wheels test the smoke checker without a build-tool dependency."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv
import zipfile

from junit2context import __version__


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smoke_wheel", ROOT / "scripts/smoke_wheel.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class WheelSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wheel-smoke-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.environment = cls.root / "venv"
        cls.cwd = cls.root / "unrelated"
        cls.cwd.mkdir()
        # No site-packages from the interpreter running the tests are inherited.
        venv.EnvBuilder(with_pip=True).create(cls.environment)
        cls.env = smoke.clean_environment()

    def install_fixture(self, *, entrypoint=True, module=True):
        """Assemble only project code and minimal synthetic wheel metadata."""
        wheel = self.root / f"junit2context-{__version__}-py3-none-any.whl"
        info = f"junit2context-{__version__}.dist-info"
        with zipfile.ZipFile(wheel, "w") as archive:
            for path in sorted((ROOT / "src/junit2context").glob("*.py")):
                if module or path.name != "__main__.py":
                    archive.write(path, f"junit2context/{path.name}")
            archive.writestr(f"{info}/METADATA",
                             f"Metadata-Version: 2.1\nName: junit2context\nVersion: {__version__}\n")
            archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: synthetic-test\n"
                              "Root-Is-Purelib: true\nTag: py3-none-any\n")
            if entrypoint:
                archive.writestr(f"{info}/entry_points.txt",
                                 "[console_scripts]\njunit2context = junit2context.cli:main\n")
            archive.writestr(f"{info}/RECORD", "".join(
                f"{name},,\n" for name in [*archive.namelist(), f"{info}/RECORD"]
            ))
        python, _ = smoke.venv_commands(self.environment)
        smoke.run([str(python), "-m", "pip", "--isolated", "install", "--no-index",
                   "--no-deps", "--force-reinstall", str(wheel)], self.cwd, self.env)

    def test_installed_fixture_passes_from_unrelated_directory(self):
        self.install_fixture()
        origins = smoke.check_installed(self.environment, self.cwd, __version__, self.env)
        self.assertEqual(origins["metadata_version"], __version__)
        self.assertTrue(Path(origins["package"]).is_relative_to(self.environment))

    def test_missing_console_entrypoint_fails(self):
        self.install_fixture(entrypoint=False)
        _, console = smoke.venv_commands(self.environment)
        self.assertFalse(console.exists())
        with self.assertRaisesRegex(smoke.SmokeError, "Cannot run.*junit2context"):
            smoke.check_installed(self.environment, self.cwd, __version__, self.env)

    def test_missing_module_entrypoint_fails(self):
        self.install_fixture(module=False)
        with self.assertRaisesRegex(smoke.SmokeError, "Command failed.*exit 1") as caught:
            smoke.check_installed(self.environment, self.cwd, __version__, self.env)
        self.assertIn("junit2context.__main__", str(caught.exception))
        self.assertIn("stderr:", str(caught.exception))

    def test_wrong_expected_version_fails(self):
        self.install_fixture()
        with self.assertRaisesRegex(smoke.SmokeError, "expected wheel version 999"):
            smoke.check_installed(self.environment, self.cwd, "999", self.env)

    def test_malformed_installed_cli_json_reports_command_cwd_and_output(self):
        self.install_fixture()
        origins = smoke.check_installed(self.environment, self.cwd, __version__, self.env)
        cli = Path(origins["cli"])
        original = cli.read_text(encoding="utf-8")
        self.addCleanup(cli.write_text, original, encoding="utf-8")
        cli.write_text(original.replace('content = json.dumps({',
                       'print("synthetic malformed JSON"); content = json.dumps({'),
                       encoding="utf-8")
        with self.assertRaises(smoke.SmokeError) as caught:
            smoke.check_installed(self.environment, self.cwd, __version__, self.env)
        for text in ("Invalid JSON", str(self.cwd), "junit2context", "--format json",
                     "stdout:", "synthetic malformed JSON"):
            self.assertIn(text, str(caught.exception))

    def test_checkout_import_is_rejected(self):
        self.install_fixture()
        with patch.object(smoke, "PROBE", smoke.PROBE.replace("junit2context.__file__",
                          repr(str(ROOT / "src/junit2context/__init__.py")))):
            with self.assertRaisesRegex(smoke.SmokeError, "package resolves outside"):
                smoke.check_installed(self.environment, self.cwd, __version__, self.env)

    def test_environment_strips_python_overrides_without_mutating_parent(self):
        with patch.dict(os.environ, {"PYTHONPATH": str(ROOT / "src"),
                                     "PYTHONHOME": "/synthetic-invalid-home"}):
            env = smoke.clean_environment()
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("PYTHONHOME", env)
            self.assertIn("PYTHONHOME", os.environ)

    def test_requires_exactly_one_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(smoke.SmokeError, "found 0"):
                smoke.wheel_artifact(root)
            (root / "one.whl").touch()
            self.assertEqual(smoke.wheel_artifact(root), root / "one.whl")
            (root / "two.whl").touch()
            with self.assertRaisesRegex(smoke.SmokeError, "found 2"):
                smoke.wheel_artifact(root)

    def test_command_failure_reports_command_cwd_and_output(self):
        with self.assertRaises(smoke.SmokeError) as caught:
            smoke.run([sys.executable, "-c",
                       "import sys; print('synthetic stdout'); "
                       "print('synthetic stderr', file=sys.stderr); sys.exit(7)"],
                      self.cwd, self.env)
        for text in ("exit 7", str(self.cwd), "-c", "synthetic stdout", "synthetic stderr"):
            self.assertIn(text, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
