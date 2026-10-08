"""Build and exercise the installed wheel independently of the source checkout."""

from email.parser import BytesParser
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REPORT = '''<testsuite name="wheel smoke" tests="3" failures="1" errors="1">
<testcase classname="SmokeClass" name="failed case">
<failure message="expected two">AssertionError: expected 2, got 1
TOKEN=synthetic-wheel-secret</failure></testcase>
<testcase classname="SmokeClass" name="setup case">
<error message="setup failed">RuntimeError: synthetic setup error</error></testcase>
<testcase name="passing case"/>
</testsuite>'''

PROBE = '''import importlib.metadata as metadata
import json
import sys
import junit2context
import junit2context.cli
distribution = metadata.distribution("junit2context")
print(json.dumps({
    "prefix": sys.prefix,
    "package": junit2context.__file__,
    "cli": junit2context.cli.__file__,
    "distribution": str(distribution.locate_file("")),
    "module_version": junit2context.__version__,
    "metadata_version": distribution.version,
}))
'''


class SmokeError(RuntimeError):
    """An installed-artifact check failed."""


def clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8")
    except OSError as exc:
        raise SmokeError(f"Cannot run {shlex.join(command)} in {cwd}: {exc}") from exc
    if result.returncode:
        raise SmokeError(f"Command failed (exit {result.returncode}) in {cwd}:\n"
                         f"{shlex.join(command)}\n"
                         f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result.stdout


def wheel_artifact(directory: Path) -> Path:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise SmokeError(f"Expected exactly one built wheel in {directory}; "
                         f"found {len(wheels)}: {[path.name for path in wheels]}")
    return wheels[0]


def parse_json(output: str, command: list[str], cwd: Path):
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"Invalid JSON from {shlex.join(command)} in {cwd}: {exc}\n"
                         f"stdout:\n{output}") from exc


def wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise SmokeError(f"Expected one distribution metadata file in {wheel.name}")
        fields = BytesParser().parsebytes(archive.read(metadata[0]))
    if fields["Name"] != "junit2context" or not fields["Version"]:
        raise SmokeError(f"Expected junit2context name and version in {wheel.name}")
    return fields["Version"]


def venv_commands(environment: Path) -> tuple[Path, Path]:
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    return (scripts / ("python.exe" if os.name == "nt" else "python"),
            scripts / ("junit2context.exe" if os.name == "nt" else "junit2context"))


def check_installed(environment: Path, cwd: Path, expected_version: str,
                    env: dict[str, str]) -> dict[str, str]:
    python, console = venv_commands(environment)
    probe_command = [str(python), "-I", "-c", PROBE]
    origins = parse_json(run(probe_command, cwd, env), probe_command, cwd)
    if Path(origins["prefix"]).resolve() != environment.resolve():
        raise SmokeError(f"Interpreter is outside the fresh venv: {origins}")
    for name in ("package", "cli", "distribution"):
        if not Path(origins[name]).resolve().is_relative_to(environment.resolve()):
            raise SmokeError(f"{name} resolves outside the fresh venv: {origins[name]}")
    for name in ("module_version", "metadata_version"):
        if origins[name] != expected_version:
            raise SmokeError(f"{name}: expected wheel version {expected_version}, "
                             f"got {origins[name]}")

    (cwd / "report.xml").write_text(REPORT, encoding="utf-8")
    entrypoints = ([str(console)], [str(python), "-m", "junit2context"])
    for command in entrypoints:
        version = run([*command, "--version"], cwd, env).strip()
        if version != f"junit2context {expected_version}":
            raise SmokeError(f"Unexpected version from {shlex.join(command)}: {version!r}")
        markdown = run([*command, "report.xml", "--format", "markdown"], cwd, env)
        required = ("# Test failure context", "2 unique failure(s).", "failed case",
                    "setup case", "SmokeClass", "Kind: failure", "Kind: error",
                    "expected two", "setup failed", "AssertionError: expected 2, got 1",
                    "RuntimeError: synthetic setup error", "TOKEN=[REDACTED]")
        if (any(text not in markdown for text in required)
                or "passing case" in markdown or "synthetic-wheel-secret" in markdown):
            raise SmokeError(f"Unexpected Markdown from {shlex.join(command)}:\n{markdown}")
        json_command = [*command, "report.xml", "--format", "json"]
        output = run(json_command, cwd, env)
        data = parse_json(output, json_command, cwd)
        expected = {
            "schema_version": 1, "failure_count": 2,
            "truncated_details": 0, "truncated_messages": 0,
            "failures": [
                {"source": "report.xml", "suite": "wheel smoke", "name": "failed case",
                 "classname": "SmokeClass", "kind": "failure", "message": "expected two",
                 "details": "AssertionError: expected 2, got 1\nTOKEN=[REDACTED]"},
                {"source": "report.xml", "suite": "wheel smoke", "name": "setup case",
                 "classname": "SmokeClass", "kind": "error", "message": "setup failed",
                 "details": "RuntimeError: synthetic setup error"},
            ],
        }
        if data != expected:
            raise SmokeError(f"Unexpected JSON from {shlex.join(command)}:\n{output}")
    return origins


def main() -> int:
    env = clean_environment()
    try:
        with tempfile.TemporaryDirectory(prefix="junit2context-wheel-") as directory:
            temporary = Path(directory).resolve()
            if temporary.is_relative_to(ROOT):
                raise SmokeError("Temporary directory is inside the checkout; "
                                 "set TMPDIR/TEMP to an unrelated directory")
            artifacts, cwd = temporary / "dist", temporary / "work"
            artifacts.mkdir()
            cwd.mkdir()
            run([sys.executable, "-m", "build", "--wheel", "--outdir", str(artifacts),
                 str(ROOT)], cwd, env)
            wheel = wheel_artifact(artifacts)
            environment = temporary / "venv"
            run([sys.executable, "-m", "venv", str(environment)], cwd, env)
            python, _ = venv_commands(environment)
            run([str(python), "-m", "pip", "--isolated", "install", "--no-deps",
                 "--no-index", str(wheel)], cwd, env)
            origins = check_installed(environment, cwd, wheel_version(wheel), env)
            print(f"Wheel smoke passed: {wheel.name}")
            print(f"Installed package: {origins['package']}")
            print(f"Installed CLI module: {origins['cli']}")
            print(f"Distribution: {origins['distribution']}; "
                  f"version: {origins['metadata_version']}")
            print("Console and module: --version, synthetic Markdown and JSON passed "
                  "outside the checkout, without PYTHONPATH/PYTHONHOME.")
    except (SmokeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"Wheel smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
