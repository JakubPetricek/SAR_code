#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
from pathlib import Path

def create_bmp(infile: Path, meta_file: Path, overwrite=False, colormap="gray",
               input_format="float", output_format="real", mm=1):
    """Call PolSARpro create_bmp_file.exe for a single input file."""
    with open(meta_file) as f:
        meta = json.load(f)

    rows = int(meta["rows"])
    cols = int(meta["cols"])
    fnr  = int(meta["fnr"])
    fnc  = int(meta["fnc"])
    ofr  = int(meta["ofr"])
    ofc  = int(meta["ofc"])

    outfile = infile.with_suffix(".bmp")
    if outfile.exists() and not overwrite:
        print(f"[SKIP] {outfile.name} already exists.")
        return

    cmd = [
        "/home/jpe128/polsarpro/Soft/bin/bmp_process/create_bmp_file.exe",
        "-if", str(infile),
        "-of", str(outfile),
        "-ift", input_format,
        "-oft", output_format,
        "-clm", colormap,
        "-nc", str(cols),
        "-ofr", str(ofr),
        "-ofc", str(ofc),
        "-fnr", str(fnr),
        "-fnc", str(fnc),
        "-min", "0",
        "-max", "1",
        "-mm", str(mm),
    ]

    print(f"[INFO] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode not in (0, 1):
        print(f"[ERROR] Failed for {infile.name} (rc={proc.returncode})")
        print(proc.stderr)
    else:
        print(f"[OK] Created {outfile.name}")

def main():
    parser = argparse.ArgumentParser(
        description="Batch-create BMP quicklooks from PolSARpro .bin files."
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Path to folder containing .bin files and metadata.json"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing BMPs"
    )
    parser.add_argument(
        "--colormap", default="gray",
        help="Colormap (gray, grayrev, jet, hsv, etc.)"
    )
    parser.add_argument(
        "--ift", default="float",
        help="Input format (float, cmplx, int)"
    )
    parser.add_argument(
        "--oft", default="real",
        help="Output format (real, imag, mod, pha, db10, db20)"
    )
    parser.add_argument(
        "--mm", type=int, default=1,
        help="Min-max determination (0–3), default 1"
    )
    args = parser.parse_args()

    folder = Path(args.input).resolve()
    if not folder.is_dir():
        sys.exit(f"[ERROR] Not a directory: {folder}")

    # Recursively find all .bin files
    bin_files = sorted(folder.rglob("*.bin"))
    if not bin_files:
        sys.exit(f"[ERROR] No .bin files found under {folder}")

    print(f"[INFO] Found {len(bin_files)} .bin files under {folder}")

    for infile in bin_files:
        meta_file = infile.parent / "metadata.json"
        if not meta_file.exists():
            print(f"[WARN] No metadata.json in {infile.parent}, skipping {infile.name}")
            continue
        create_bmp(infile, meta_file,
                   overwrite=args.overwrite,
                   colormap=args.colormap,
                   input_format=args.ift,
                   output_format=args.oft,
                   mm=args.mm)

if __name__ == "__main__":
    main()