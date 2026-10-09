"""Keep third_party/epson_print_conf in step with upstream releases.

    python tools/update_upstream.py            check: is there a newer release?
    python tools/update_upstream.py --apply    download it, show which printer
                                               models changed, replace the
                                               vendored files, run the tests
    python tools/update_upstream.py --verify   download the release we vendor
                                               and confirm our copy is identical

The app never fetches printer parameters at run time: new parameters reach
users only through a release that passed the tests.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "third_party" / "epson_print_conf"
REPO = "Ircama/epson_print_conf"
FILES = ("epson_print_conf.py", "LICENSE")

# Run inside a separate interpreter so old and new versions never mix.
DUMP_MODELS = r"""
import json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, sys.argv[1])
import epson_print_conf as epc
p = epc.EpsonPrinter()
def plain(v):
    if isinstance(v, (bytes, bytearray)): return v.hex()
    if isinstance(v, range): return [v.start, v.stop, v.step]
    if isinstance(v, dict): return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [plain(x) for x in v]
    return v
keys = ("read_key", "write_key", "main_waste", "borderless_waste", "raw_waste_reset", "serial_number")
print(json.dumps({m: plain({k: p.PRINTER_CONFIG[m].get(k) for k in keys}) for m in sorted(p.valid_printers)}))
"""


def api(path):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", headers={"User-Agent": "padreset"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def vendored():
    """{'tag': ..., 'commit': ...} from UPSTREAM.txt."""
    info = {}
    for line in (VENDOR / "UPSTREAM.txt").read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def download(tag, dest):
    for name in FILES:
        url = f"https://raw.githubusercontent.com/{REPO}/{tag}/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": "padreset"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            (dest / name).write_bytes(resp.read())


def models(directory):
    out = subprocess.run([sys.executable, "-I", "-c", DUMP_MODELS, str(directory)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    current = vendored()
    latest = api("releases/latest")["tag_name"]
    print(f"vendored: {current.get('tag')}   latest upstream release: {latest}")

    if args.verify:
        with tempfile.TemporaryDirectory() as tmp:
            download(current["tag"], Path(tmp))
            for name in FILES:
                same = sha256(Path(tmp) / name) == sha256(VENDOR / name)
                print(f"  {name}: {'identical to upstream' if same else 'DIFFERS from upstream'}")
        return

    if latest == current.get("tag"):
        print("Up to date.")
        return
    if not args.apply:
        print("A newer release exists. Run with --apply to update.")
        return

    commit = api(f"commits/{latest}")["sha"]
    with tempfile.TemporaryDirectory() as tmp:
        new_dir = Path(tmp)
        download(latest, new_dir)
        old_m, new_m = models(VENDOR), models(new_dir)
        added = sorted(set(new_m) - set(old_m))
        removed = sorted(set(old_m) - set(new_m))
        changed = sorted(m for m in set(old_m) & set(new_m) if old_m[m] != new_m[m])
        print(f"models: {len(old_m)} -> {len(new_m)}")
        print(f"  added ({len(added)}): {', '.join(added) or '-'}")
        print(f"  removed ({len(removed)}): {', '.join(removed) or '-'}")
        print(f"  parameters changed ({len(changed)}): {', '.join(changed) or '-'}")
        for name in FILES:
            (VENDOR / name).write_bytes((new_dir / name).read_bytes())

    (VENDOR / "UPSTREAM.txt").write_text(
        f"repo: https://github.com/{REPO}\ntag: {latest}\ncommit: {commit}\n"
        "files: epson_print_conf.py (unmodified), LICENSE\n", encoding="utf-8")
    print("Vendored files replaced. Running tests...")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT)
    if result.returncode:
        print("TESTS FAILED: do not release. Revert with: git checkout third_party")
        sys.exit(1)
    print("Tests passed. Update the tag in NOTICE.md, then run .\\build.ps1")


if __name__ == "__main__":
    main()
