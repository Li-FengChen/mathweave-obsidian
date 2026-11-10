"""Download pinned renderer resources once for offline preview."""
import hashlib
import io
import json
import tarfile
import urllib.request
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "assets" / "vendor"
PACKAGES = {"mathjax": "3.2.2", "marked": "12.0.2", "dompurify": "3.2.6"}


def main():
    VENDOR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, version in PACKAGES.items():
        url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        cache = ROOT / ".qa" / "downloads" / f"{name}-{version}.tgz"
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            payload = cache.read_bytes()
        else:
            for attempt in range(4):
                try:
                    payload = urllib.request.urlopen(url, timeout=60).read()
                    cache.write_bytes(payload)
                    break
                except OSError:
                    if attempt == 3:
                        raise
                    time.sleep(2)
        manifest[name] = dict(version=version, url=url, sha256=hashlib.sha256(payload).hexdigest())
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = member.name.removeprefix("package/")
                keep = (name == "mathjax" and relative.startswith("es5/")) or (name == "marked" and relative == "lib/marked.umd.js") or (name == "dompurify" and relative == "dist/purify.min.js") or relative.upper().startswith(("LICENSE", "COPYING"))
                if not keep or not member.isfile():
                    continue
                target = (VENDOR / name / relative).resolve()
                if not target.is_relative_to(VENDOR.resolve()):
                    raise ValueError("Unsafe asset path")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        print(f"Saved {name} {version}")
    (VENDOR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
