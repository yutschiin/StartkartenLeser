"""Fetch and verify the pinned, local DE·HTR v2 runtime assets."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from urllib.request import urlopen


REPOSITORY = "naeyn/de-htr-web-v2"
REVISION = "6241c1ff0fd42725e0dc46fcd3217469cac851bb"
BASE_URL = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}"
ASSET_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "startkartenleser"
    / "assets"
    / "models"
    / "de-htr-v2"
)
CHECKSUMS = {
    "model.onnx": "b576a0a1281b9be46b2574028b75575e041b7d7cb650f063886e733467cc1499",
    "config.json": "4ebd69d9d27b398ea3997b031318accc13123f6a8950def1fedc6e364cb758fa",
    "README.md": "8917218b8fe3a5e37fe59d2bd106a70b2b11503b32bf795de657e363fd32ada6",
    "NOTICE-training-data.md": "189ca72a041dc992c1d85db3bf5158dd9e0ddd7ae11454488d0d7a020d297bf6",
}
EXTERNAL_LICENSES = {
    "LICENSE-Apache-2.0.txt": (
        "https://www.apache.org/licenses/LICENSE-2.0.txt",
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    ),
}
CHUNK_SIZE = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified(path: Path, expected: str) -> bool:
    return path.is_file() and sha256(path) == expected


def download(
    name: str,
    expected_hash: str | None = None,
    *,
    url: str | None = None,
) -> None:
    destination = ASSET_DIR / name
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    if expected_hash and verified(destination, expected_hash):
        print(f"Verified existing {name}")
        return

    temporary_path: Path | None = None
    try:
        with urlopen(url or f"{BASE_URL}/{name}", timeout=60) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=ASSET_DIR, prefix=f".{name}.", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                digest = hashlib.sha256()
                while chunk := response.read(CHUNK_SIZE):
                    temporary.write(chunk)
                    digest.update(chunk)

        if expected_hash and digest.hexdigest() != expected_hash:
            raise ValueError(
                f"SHA-256 mismatch for {name}: expected {expected_hash}, "
                f"received {digest.hexdigest()}"
            )
        os.replace(temporary_path, destination)
        print(f"Fetched {name}" + (" and verified its SHA-256" if expected_hash else ""))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def check_assets() -> bool:
    ok = True
    for name, expected in CHECKSUMS.items():
        path = ASSET_DIR / name
        if verified(path, expected):
            print(f"OK {name} sha256={expected}")
        else:
            print(f"Missing or invalid model asset: {path}", file=sys.stderr)
            ok = False
    for name, (_, expected) in EXTERNAL_LICENSES.items():
        path = ASSET_DIR / name
        if verified(path, expected):
            print(f"OK {name} sha256={expected}")
        else:
            print(f"Missing or invalid license file: {path}", file=sys.stderr)
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify already provisioned model files without network access",
    )
    args = parser.parse_args()
    if args.check:
        return 0 if check_assets() else 1

    try:
        for name, expected in CHECKSUMS.items():
            download(name, expected)
        for name, (url, expected) in EXTERNAL_LICENSES.items():
            download(name, expected, url=url)
    except (OSError, URLError, ValueError) as error:
        print(f"Model provisioning failed: {error}", file=sys.stderr)
        return 1
    return 0 if check_assets() else 1


if __name__ == "__main__":
    raise SystemExit(main())
