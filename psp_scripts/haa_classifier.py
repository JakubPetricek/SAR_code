#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path
import shutil

DEFAULT_EXE = Path.home() / "polsarpro" / "Soft/bin/data_process_sngl/h_a_alpha_planes_classifier.exe"
DEFAULT_COLORMAP = Path("/home/jpe128/polsarpro/ColorMap/Planes_H_A_Alpha_ColorMap9.pal")

def find_metadata_json(folder: Path) -> Path:
    """Search for metadata.json in this folder or its parents (up to 3 levels)."""
    for level in [folder, folder.parent, folder.parent.parent]:
        m = level / "metadata.json"
        if m.exists():
            return m
    raise FileNotFoundError(f"No metadata.json found near {folder}")

def load_sizes(meta: Path) -> dict:
    """Read necessary size parameters from metadata.json."""
    with open(meta) as f:
        m = json.load(f)
    return {
        "ofr": int(m.get("ofr", 0)),
        "ofc": int(m.get("ofc", 0)),
        "fnr": int(m.get("fnr", m.get("rows", 0))),
        "fnc": int(m.get("fnc", m.get("cols", 0))),
    }

def ensure_config_in_input(folder: Path, meta_path: Path):
    """Copy config.txt from the T3 folder if the classifier expects it."""
    candidates = [
        meta_path.parent / "config.txt",
        meta_path.parent.parent / "config.txt",
    ]
    dst = folder / "config.txt"
    if not dst.exists():
        for c in candidates:
            if c.exists():
                shutil.copy2(c, dst)
                print(f"[INFO] Copied config.txt from {c}")
                return dst
    return None

def run(cmd):
    print("[INFO]", " ".join(cmd))
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.stdout:
        print(cp.stdout)
    if cp.stderr:
        print(cp.stderr, file=sys.stderr)
    if cp.returncode not in (0, 1):
        sys.exit(f"[ERROR] h_a_alpha_planes_classifier.exe failed (code={cp.returncode})")
    return cp

def main():
    ap = argparse.ArgumentParser(description="Wrapper for PolSARpro h_a_alpha_planes_classifier.exe")
    ap.add_argument("-i", "--input", required=True, help="Input directory (T3 folder containing decomposition results)")
    ap.add_argument("-o", "--output", help="Output directory (default: same as input)")
    ap.add_argument("--exe", default=str(DEFAULT_EXE), help="Path to h_a_alpha_planes_classifier.exe")
    ap.add_argument("--colormap", default=str(DEFAULT_COLORMAP), help="Path to the 9-color colormap palette file")
    ap.add_argument("--errf", help="Path for memory error file (default: <output>/MemoryAllocError.txt)")
    ap.add_argument("--meta", help="Path to metadata.json (default: searched automatically)")
    ap.add_argument("--mask", help="Path to mask_valid_pixels.bin (default: searched in input folder)")
    ap.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files")
    args = ap.parse_args()

    in_dir = Path(args.input).resolve()
    if not in_dir.exists():
        sys.exit(f"[ERROR] Input directory not found: {in_dir}")
    out_dir = Path(args.output).resolve() if args.output else in_dir

    # locate metadata and image sizes
    meta_path = Path(args.meta).resolve() if args.meta else find_metadata_json(in_dir)
    sizes = load_sizes(meta_path)

    # ensure config.txt exists in the input folder
    tmp_cfg = ensure_config_in_input(in_dir, meta_path)

    exe = Path(args.exe).resolve()
    if not exe.exists():
        sys.exit(f"[ERROR] Executable not found: {exe}")
    colormap = Path(args.colormap).resolve()
    if not colormap.exists():
        sys.exit(f"[ERROR] Colormap not found: {colormap}")

    errf = Path(args.errf).resolve() if args.errf else (out_dir / "MemoryAllocError.txt")
    mask = Path(args.mask).resolve() if args.mask else (in_dir / "mask_valid_pixels.bin")
    if not mask.exists():
        sys.exit(f"[ERROR] Mask file not found: {mask}")

    # build the command
    cmd = [
        str(exe),
        "-id", str(in_dir),
        "-od", str(out_dir),
        "-ofr", str(sizes["ofr"]),
        "-ofc", str(sizes["ofc"]),
        "-fnr", str(sizes["fnr"]),
        "-fnc", str(sizes["fnc"]),
        "-hal", "1",
        "-anal", "1",
        "-han", "1",
        "-clm", str(colormap),
        "-errf", str(errf),
        "-mask", str(mask)
    ]

    run(cmd)

    # cleanup temp config.txt if copied
    if tmp_cfg and tmp_cfg.exists():
        tmp_cfg.unlink()
        print("[INFO] Removed temporary config.txt")

    print(f"[OK] H/A/α classification complete → {out_dir}")

if __name__ == "__main__":
    main()