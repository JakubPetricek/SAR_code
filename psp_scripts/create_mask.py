#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_EXE = Path.home() / "polsarpro" / "Soft" / "bin" / "tools" / "create_mask_valid_pixels.exe"

def find_metadata_json(id_dir: Path, meta_dir: str | None) -> Path:
    """Find metadata.json near the input directory or in user-specified directory."""
    if meta_dir:
        p = Path(meta_dir)
        p = p / "metadata.json" if p.is_dir() else p
        if p.exists():
            return p
        raise RuntimeError(f"--meta-dir set but no metadata.json at: {p}")

    # common neighbors: base, T3/, parent, parent/T3
    base = id_dir
    candidates = [
        base / "metadata.json",
        base / "T3" / "metadata.json",
        id_dir.parent / "metadata.json",
        id_dir.parent / "T3" / "metadata.json",
    ]
    for c in candidates:
        if c.exists():
            return c

    # walk upward a few levels
    cur = id_dir
    for _ in range(3):
        m = cur / "metadata.json"
        if m.exists():
            return m
        cur = cur.parent

    raise RuntimeError(f"metadata.json not found near {id_dir}. Use --meta-dir to point to the T3 folder.")

def load_sizes(meta_path: Path) -> dict:
    m = json.loads(meta_path.read_text())
    rows = int(m.get("rows", m.get("fnr")))
    cols = int(m.get("cols", m.get("fnc")))
    return {
        "ofr": int(m.get("ofr", 0)),
        "ofc": int(m.get("ofc", 0)),
        "fnr": int(m.get("fnr", rows)),
        "fnc": int(m.get("fnc", cols)),
        "rows": int(rows),
        "cols": int(cols),
    }

def ensure_config_in_input(id_dir: Path, meta_path: Path) -> Path | None:
    """
    Some PSP tools expect config.txt in the *input* directory.
    If it exists next to metadata.json, copy it in temporarily.
    """
    src_candidates = [
        meta_path.parent / "config.txt",
        meta_path.parent.parent / "T3" / "config.txt",
        id_dir.parent / "config.txt",
    ]
    for src in src_candidates:
        if src.exists():
            dst = id_dir / "config.txt"
            if not dst.exists():
                shutil.copy2(src, dst)
                return dst
            return None
    return None

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("[INFO]", " ".join(cmd))
    return subprocess.run(cmd, text=True, capture_output=True)

def main():
    ap = argparse.ArgumentParser(description="Wrapper for PolSARpro create_mask_valid_pixels.exe")
    ap.add_argument("-i", "--input", required=True, help="Input directory (T3/C3 folder)")
    ap.add_argument("-o", "--output", help="Output directory (default: same as input)")
    ap.add_argument("--idf", default="T3", choices=["T3", "C3"], help="Input data format (default: T3)")
    ap.add_argument("--meta-dir", help="Directory containing metadata.json (usually the T3 folder)")
    ap.add_argument("--exe", help="Path to create_mask_valid_pixels.exe")
    ap.add_argument("--errf", help="Path for memory error log (default: <output>/MemoryAllocError.txt)")
    ap.add_argument("--overwrite", action="store_true", help="Allow existing non-empty output dir")
    args = ap.parse_args()

    id_dir = Path(args.input).resolve()
    if not id_dir.is_dir():
        sys.exit(f"[ERROR] not a directory: {id_dir}")

    od_dir = Path(args.output).resolve() if args.output else id_dir
    if od_dir.exists() and not args.overwrite and any(od_dir.iterdir()):
        print(f"[WARN] output exists and not empty: {od_dir} (use --overwrite if intended)")
    od_dir.mkdir(parents=True, exist_ok=True)

    meta_path = find_metadata_json(id_dir, args.meta_dir)
    sizes = load_sizes(meta_path)

    # Ensure config.txt in input (some tools expect it there)
    tmp_cfg = ensure_config_in_input(id_dir, meta_path)

    exe = Path(args.exe).resolve() if args.exe else DEFAULT_EXE
    if not exe.exists():
        sys.exit(f"[ERROR] binary not found: {exe}")

    errf = Path(args.errf).resolve() if args.errf else (od_dir / "MemoryAllocError.txt")

    cmd = [
        str(exe),
        "-id", str(id_dir),
        "-od", str(od_dir),
        "-idf", str(args.idf),
        "-ofr", str(sizes["ofr"]),
        "-ofc", str(sizes["ofc"]),
        "-fnr", str(sizes["fnr"]),
        "-fnc", str(sizes["fnc"]),
        "-errf", str(errf),
    ]

    before = set(p.name for p in od_dir.glob("*.bin"))
    cp = run(cmd)

    # PSP often returns 1 on “success”. Consider success if a new mask appears and no fatal banner.
    banner = "A processing error occured"
    after = set(p.name for p in od_dir.glob("*.bin"))
    created = sorted(after - before)

    # Look for an expected output (mask name varies across modules; common name below):
    expected_names = {"mask_valid_pixels.bin", "ValidPixelsMask.bin"}
    produced_mask = [n for n in created if n in expected_names] or [n for n in after if n in expected_names]

    ok = (cp.returncode in (0, 1)) and banner not in (cp.stdout + cp.stderr)
    if produced_mask:
        ok = True

    if not ok:
        if cp.stdout:
            print(cp.stdout)
        if cp.stderr:
            print(cp.stderr, file=sys.stderr)
        sys.exit("[ERROR] create_mask_valid_pixels failed or produced no mask output.")

    print(f"[OK] mask creation complete. Outputs in: {od_dir}")
    if produced_mask:
        print("[OK] mask file(s): " + ", ".join(produced_mask))

    # optional cleanup: remove temporary config.txt we copied into input
    if tmp_cfg and tmp_cfg.exists():
        try:
            tmp_cfg.unlink()
            print("[INFO] removed temporary config.txt from input.")
        except Exception:
            pass

if __name__ == "__main__":
    main()