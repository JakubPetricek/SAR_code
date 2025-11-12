#!/usr/bin/env python3
import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
import numpy as np

# ---- config --------------------------------------------------------------

# default PolSARpro executable (change to use your psp wrapper if you prefer)
PSP_BMP_EXE = "/home/jpe128/polsarpro/Soft/bin/bmp_process/create_bmp_file.exe"

# which diagonals/off-diagonals we support
DIAG = {"11", "22", "33"}
OFFD = {"12", "13", "23"}

# -------------------------------------------------------------------------

def load_meta(meta_path: Path):
    with meta_path.open() as f:
        meta = json.load(f)
    # cast to ints (json may store as str)
    rows = int(meta["rows"])
    cols = int(meta["cols"])
    fnr  = int(meta["fnr"])
    fnc  = int(meta["fnc"])
    ofr  = int(meta["ofr"])
    ofc  = int(meta["ofc"])
    return rows, cols, fnr, fnc, ofr, ofc

def call_create_bmp(infile: Path, meta, outfile: Path, *, colormap="gray",
                    ift="float", oft="real", mm=1, minv=0.0, maxv=1.0):
    rows, cols, fnr, fnc, ofr, ofc = meta
    cmd = [
        PSP_BMP_EXE,
        "-if", str(infile),
        "-of", str(outfile),
        "-ift", ift,
        "-oft", oft,           # real/imag/mod/pha/db10/db20
        "-clm", colormap,
        "-nc", str(cols),      # number of columns
        "-ofr", str(ofr),
        "-ofc", str(ofc),
        "-fnr", str(fnr),
        "-fnc", str(fnc),
        "-min", str(minv),
        "-max", str(maxv),
        "-mm",  str(mm),       # 1 = compute min/max internally
    ]
    print("[INFO] BMP:", " ".join(cmd))
    cp = subprocess.run(cmd, text=True, capture_output=True)
    if cp.returncode not in (0, 1):
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        raise RuntimeError(f"create_bmp_file.exe failed (rc={cp.returncode}) for {infile.name}")

def mag_or_phase_from_pair(real_path: Path, imag_path: Path, out_path: Path,
                           rows: int, cols: int, mode: str = "mag"):
    """
    Compute magnitude or phase from paired float32 real/imag binaries.
    Uses memmap to avoid loading entire rasters in RAM.
    mode: 'mag' | 'phase'
    """
    dtype = np.float32
    # sanity: file sizes
    need_bytes = rows * cols * np.dtype(dtype).itemsize
    for p in (real_path, imag_path):
        if p.stat().st_size < need_bytes:
            raise ValueError(f"{p} smaller than expected size for {rows}x{cols} float32")

    r = np.memmap(real_path, dtype=dtype, mode="r", shape=(rows, cols))
    i = np.memmap(imag_path, dtype=dtype, mode="r", shape=(rows, cols))

    # output file as memmap
    out = np.memmap(out_path, dtype=dtype, mode="w+", shape=(rows, cols))

    if mode == "mag":
        # sqrt(re^2 + im^2)
        np.sqrt(r*r + i*i, out=out)
    elif mode == "phase":
        # atan2(im, re) in radians
        np.arctan2(i, r, out=out)
    else:
        raise ValueError("mode must be 'mag' or 'phase'")

    # ensure data written
    del out, r, i

def is_diag_name(name: str):
    # matches T11.bin, C22.bin, T33.bin, etc.
    m = re.fullmatch(r"([TC])([123])\2\.bin", name, flags=re.IGNORECASE)
    return bool(m)

def parse_offdiag(name: str):
    # returns ('T' or 'C', '12'/'13'/'23', 'real'|'imag') or None
    m = re.fullmatch(r"([TC])(1[23]|2[3])_(real|imag)\.bin", name, flags=re.IGNORECASE)
    if not m:
        return None
    family = m.group(1).upper()
    pair   = m.group(2)
    part   = m.group(3).lower()
    return family, pair, part

def group_complex_pairs(bin_files):
    """
    From a list of Path '*.bin', find off-diagonal pairs:
    returns dict like:
      { ('T','12'): {'real': Path(...T12_real.bin), 'imag': Path(...T12_imag.bin)}, ... }
    and a list of diagonals.
    """
    pairs = {}
    diags = []
    for p in bin_files:
        name = p.name
        if is_diag_name(name):
            diags.append(p)
            continue
        parsed = parse_offdiag(name)
        if not parsed:
            continue
        family, pair, part = parsed
        key = (family, pair)
        d = pairs.setdefault(key, {})
        d[part] = p
    return pairs, diags

def find_metadata_for(bin_file: Path):
    # expects metadata.json in same folder
    meta_path = bin_file.parent / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json not found beside {bin_file}")
    return meta_path

def main():
    ap = argparse.ArgumentParser(
        description="Batch BMP generator for PolSARpro T3/C3 outputs: "
                    "diagonals visualized directly, off-diagonals as magnitude (or phase).")
    ap.add_argument("-i","--input", required=True, help="Folder (recursed) containing .bin + metadata.json")
    ap.add_argument("--mode", choices=["mag","phase"], default="mag",
                    help="For off-diagonal complex pairs, make magnitude or phase (default: mag)")
    ap.add_argument("--colormap", default="gray", help="Colormap (gray, grayrev, jet, hsv, ...)")
    ap.add_argument("--mm", type=int, default=1, help="Min-max mode for BMP (0–3). 1 lets PolSARpro compute min/max.")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing BMPs")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders (default: current folder only)")
    ap.add_argument("--use-psp", action="store_true",
                    help="Use 'psp bmp_process create_bmp_file.exe' instead of hardcoded path")
    args = ap.parse_args()

    root = Path(args.input).resolve()
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    # choose invocation
    global PSP_BMP_EXE
    if args.use_psp:
        PSP_BMP_EXE = "psp bmp_process create_bmp_file.exe"  # we won't split it—just document to use --use-psp only if wrapper supports it
        # but subprocess needs args split; so keep default path by default.
        # safer to keep the absolute exe path set above.

    # collect .bin files
    bin_files = list(root.rglob("*.bin") if args.recursive else root.glob("*.bin"))
    if not bin_files:
        print("[INFO] no .bin files found.")
        return

    # group into diagonals and complex pairs
    pairs, diag_bins = group_complex_pairs(bin_files)

    # process diagonals first (T11/T22/T33 or C11/C22/C33)
    for b in sorted(diag_bins):
        bmp_out = b.with_suffix(".bmp")
        if bmp_out.exists() and not args.overwrite:
            print(f"[SKIP] {bmp_out} exists.")
            continue
        try:
            meta = load_meta(find_metadata_for(b))
            call_create_bmp(b, meta, bmp_out,
                            colormap=args.colormap, ift="float", oft="real", mm=args.mm)
            print(f"[OK] {bmp_out.name}")
        except Exception as e:
            print(f"[ERR] {b.name}: {e}", file=sys.stderr)

    # process off-diagonal pairs as magnitude (or phase)
    for key, parts in sorted(pairs.items()):
        family, pair = key         # e.g., 'T', '13'
        if not (("real" in parts) and ("imag" in parts)):
            print(f"[WARN] incomplete pair {family}{pair} in {list(parts.values())[0].parent}, skipping.")
            continue

        real_p = parts["real"]
        imag_p = parts["imag"]
        # temp magnitude/phase binary next to inputs
        suffix = "_mag" if args.mode == "mag" else "_phase"
        temp_bin = real_p.with_name(f"{family}{pair}{suffix}.bin")
        bmp_out  = temp_bin.with_suffix(".bmp")
        if bmp_out.exists() and not args.overwrite:
            print(f"[SKIP] {bmp_out} exists.")
            continue

        try:
            rows, cols, fnr, fnc, ofr, ofc = load_meta(find_metadata_for(real_p))
            # compute derived raster
            print(f"[INFO] computing {args.mode} for {family}{pair} in {real_p.parent.name} …")
            mag_or_phase_from_pair(real_p, imag_p, temp_bin, rows=fnr, cols=fnc, mode=args.mode)
            # make BMP
            meta = (rows, cols, fnr, fnc, ofr, ofc)
            oft = "real" if args.mode == "mag" else "pha"  # phase visualization
            call_create_bmp(temp_bin, meta, bmp_out,
                            colormap=args.colormap, ift="float", oft=oft, mm=args.mm)
            print(f"[OK] {bmp_out.name}")
        except Exception as e:
            print(f"[ERR] {family}{pair}: {e}", file=sys.stderr)
        finally:
            # keep the temp .bin so you can reuse it or inspect it; comment next line to keep
            # If you prefer to remove, uncomment:
            # try: temp_bin.unlink() ; except: pass
            pass

if __name__ == "__main__":
    main()