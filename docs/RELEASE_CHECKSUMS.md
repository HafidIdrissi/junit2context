# Verify release download files

A SHA-256 manifest detects a corrupted or mismatched download. It does not
authenticate the publisher: an attacker able to replace both an artifact and its
manifest can publish matching hashes. Obtain both from the intended release and
use any independently trusted signature or provenance when available. This guide
does not claim that this project currently publishes signed releases or packages
on PyPI.

## Prepare a manifest locally

After building and reviewing the final artifacts, explicitly select the files
that will be attached to the same GitHub release. For example, from a source
checkout with Python 3.10 or newer and the two files already present in `dist/`:

```bash
python3 scripts/release_checksums.py create --output dist/SHA256SUMS \
  dist/junit2context-0.1.0.tar.gz dist/junit2context-0.1.0-py3-none-any.whl
python3 scripts/release_checksums.py check dist/SHA256SUMS
```

These are example artifact names for version 0.1.0; select the actual final
filenames and version being released. The helper uses only the standard library,
does not build or upload files, and does not create releases or use account access.
No directories are searched. Inputs can come from different local directories,
but their basenames must be unique, including case-insensitive comparisons.

Entries contain the lowercase SHA-256 digest, two spaces, and the basename, sorted
by ASCII filename with LF line endings. Artifact names must start with an ASCII
letter or digit and contain only ASCII letters, digits, dots, underscores, or
hyphens. Trailing dots and Windows device names such as `NUL.zip` are rejected.
Rename unsupported artifacts deliberately before generating the manifest.
Artifacts must be regular files, not symbolic links.

Missing/unreadable inputs and invalid names fail before creating a manifest. An
existing output is never replaced, and the manifest cannot be selected as an
input. To regenerate, first preserve the old manifest elsewhere or choose a new
output filename. Keep artifacts unchanged while hashing; if any artifact changes
afterward, regenerate and check before publishing.

The release owner can attach `SHA256SUMS` beside exactly those artifacts using
their normal reviewed release procedure. This helper performs only local
preparation; it does not grant permission to publish a release.

## Check downloaded artifacts

Place the manifest and all files it lists in one directory. On a typical Linux
or other Unix system with GNU coreutils, run **from that directory**:

```bash
sha256sum --check SHA256SUMS
```

On macOS, the equivalent command is:

```bash
shasum -a 256 --check SHA256SUMS
```

Alternatively, use Python's standard library and the helper from a source
checkout (no installation required), from any working directory:

```bash
python3 /path/to/checkout/scripts/release_checksums.py check /path/to/downloads/SHA256SUMS
```

Replace both example paths with your actual locations. On Windows, substitute
`python` for `python3` and enter the multi-line examples as one line, omitting the
shell continuation backslashes. Python resolves artifact basenames
beside the manifest. It rejects malformed entries, paths, duplicate names,
self-references, and symbolic-link artifacts. Exit status `0` means all listed
files matched, `1` means an artifact is missing, unreadable, or mismatched, and
`2` means command usage, manifest syntax, or manifest I/O failed. Creating a
manifest returns `0` on success and `2` on error.

An `OK` line means only that file's bytes match its recorded digest. If checking
fails, stop using that copy and confirm the release version and filenames;
download it again from the intended source. A mismatch alone does not establish
whether corruption, an accidental mix-up, or tampering caused it. A missing file
may simply mean you downloaded only part of the listed release. Keep failures
visible instead of accepting a partly checked release as fully verified.

## Try an unchanged and altered synthetic file

From the source checkout, with a new `checksum-demo/` directory:

```bash
python3 -c "from pathlib import Path; p = Path('checksum-demo'); p.mkdir(); (p / 'sample.zip').write_bytes(b'example artifact')"
python3 scripts/release_checksums.py create \
  --output checksum-demo/SHA256SUMS checksum-demo/sample.zip
python3 scripts/release_checksums.py check checksum-demo/SHA256SUMS
python3 -c "from pathlib import Path; Path('checksum-demo/sample.zip').write_bytes(b'altered artifact')"
python3 scripts/release_checksums.py check checksum-demo/SHA256SUMS
```

The first check prints `sample.zip: OK` and exits `0`. The last check reports
`sample.zip: FAILED (SHA-256 mismatch)` on stderr and exits `1`. This deliberately
invented byte file demonstrates integrity checking; it is not a valid ZIP or a
real release asset.
