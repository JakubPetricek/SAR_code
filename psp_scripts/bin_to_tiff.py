#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Dict

import numpy as np
import rasterio as rio
from rasterio.transform import Affine
from rasterio.crs import CRS

# ---------- ANN parsing ----------

def parse_ann(ann_path):
    rows = cols = upper_lat = upper_lon = dlat = dlon = None
    with open(ann_path) as f:
        for line in f:
            # look for keys like "grd_pwr.set_rows = 3750"
            if re.search(r"grd_pwr\.set_rows", line, re.IGNORECASE):
                rows = int(re.findall(r"\d+", line)[0]) #\d+ means any number of digits 0 to 9
            elif re.search(r"grd_pwr\.set_cols", line, re.IGNORECASE):
                cols = int(re.findall(r"\d+", line)[0])
            elif re.search(r"grd_pwr\.row_addr", line, re.IGNORECASE):
                upper_lat = re.findall(r"-?\d+(?:\.?\d+)?", line)[0]
            elif re.search(r"grd_pwr\.col_addr", line, re.IGNORECASE):
                upper_lon = re.findall(r"-?\d+(?:\.?\d+)?", line)[0]
            elif re.search(r"grd_pwr\.row_mult", line, re.IGNORECASE):
                dlat = re.findall(r"-?\d+(?:\.?\d+)?", line)[0]
            elif re.search(r"grd_pwr\.col_mult", line, re.IGNORECASE):
                dlon = re.findall(r"-?\d+(?:\.?\d+)?", line)[0]
            if rows and cols and upper_lat and upper_lon and dlat and dlon:
                break
    if not rows or not cols:
        raise ValueError(f"Could not find set_rows/cols, row/col_addr, row/col_mult in {ann_path}")
    return rows, cols, upper_lat, upper_lon, dlat, dlon


# ---------- geotransform & IO ----------

def tiff_meta(ann_path, dtype=np.float32):
    rows, cols, upper_lat, upper_lon, dlat, dlon = parse_ann(ann_path)
    t = Affine.translation(float(upper_lon), float(upper_lat))* Affine.scale(float(dlon), float(dlat))
    profile = {
        "driver": "GTiff",
        "height": rows,
        "width": cols,
        "count": 1,
        "dtype": dtype,
        "crs": CRS.from_epsg(4326),
        "transform": t,
        "compress": "deflate",
        "tiled": True,
        "predictor": 2 if np.issubdtype(dtype, np.floating) else 1,
    }
    return profile

def read_bin(path, rows, cols, dtype=np.float32) -> np.ndarray:
    arr = np.fromfile(path, dtype=dtype, count=rows * cols)
    if arr.size != rows * cols:
        raise RuntimeError(f"Size mismatch reading {path.name}: expected {rows*cols}, got {arr.size}")
    return arr.reshape((rows, cols))

def write_geotiff(out_path: Path, array, meta):
    profile = meta
    with rio.open(out_path, "w", **profile) as dst:
        dst.write(array, 1)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(
        description="Convert PolSARpro .bin rasters to GeoTIFF using a UAVSAR .ann (no ENVI headers)."
    )
    ap.add_argument("-i", "--input", required=True, help="Path to a .bin file or a folder of .bin files")
    ap.add_argument("-a", "--ann", required=True, help="Path to UAVSAR .ann file (used for size/georef)")
    ap.add_argument("-o", "--outdir", help="Output directory (default: alongside inputs)")
    ap.add_argument("--glob", default="*.bin", help="When input is a folder (default: *.bin)")
    ap.add_argument("--mask", default=None, help="A binary mask of valid pixels")
    # Overrides (use when PSP changed geometry)
    ap.add_argument("--rows", type=int, help="Override number of rows")
    ap.add_argument("--cols", type=int, help="Override number of cols")
    ap.add_argument("--ul-lon", type=float, help="Override UL pixel center longitude (deg)")
    ap.add_argument("--ul-lat", type=float, help="Override UL pixel center latitude (deg)")
    ap.add_argument("--pix-x", type=float, help="Override pixel width in degrees/pixel")
    ap.add_argument("--pix-y", type=float, help="Override pixel height in degrees/pixel (often negative)")
    ap.add_argument("--dtype", default=np.float32, help="Override dtype (default np.float32). e.g., np.float32,np.int16, np.complex64")
    ap.add_argument("--suffix", default="", help="Suffix appended before .tif")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    ann_path = Path(args.ann).resolve()
    if not ann_path.exists():
        sys.exit(f"[ERROR] .ann not found: {ann_path}")

    rows, cols, upper_lat, upper_lon, dlat, dlon = parse_ann(ann_path)

    # Resolve geometry
    if not rows or not cols:
        sys.exit("[ERROR] rows/cols missing. Provide --rows/--cols or a compatible .ann.")
    if dlon is None or dlat is None:
        sys.exit("[ERROR] pixel sizes missing. Provide --pix-x/--pix-y (x=lon, y=lat) or a compatible .ann.")
    if upper_lon is None or upper_lat is None:
        sys.exit("[ERROR] UL pixel center lon/lat missing. Provide --ul-lon/--ul-lat or a compatible .ann.")

    # Dtype/endianness
    dtype = args.dtype
    if args.mask:
        mask_path = Path(args.mask).resolve()
        if not mask_path.exists():
            sys.exit("[ERROR] Mask file not found, wrong path?")
        mask_arr = np.fromfile(file=args.mask, )
    # Collect inputs
    if in_path.is_dir():
        bin_files = sorted(in_path.glob(args.glob))
        if not bin_files:
            sys.exit(f"[ERROR] no files matched '{args.glob}' in {in_path}")
        outdir = Path(args.outdir).resolve() if args.outdir else in_path
    else:
        if in_path.suffix.lower() != ".bin":
            sys.exit("[ERROR] input must be a .bin or a folder containing .bin files")
        bin_files = [in_path]
        outdir = Path(args.outdir).resolve() if args.outdir else in_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    # Build transform once
    meta = tiff_meta(ann_path, dtype)

    mask_bool = None
    if args.mask:
        mask_path = Path(args.mask).resolve()
        if not mask_path.exists():
            sys.exit("[ERROR] Mask file not found, wrong path?")
        mask_arr = np.fromfile(mask_path, dtype=np.float32, count=rows*cols)
        if mask_arr.size != rows*cols:
            sys.exit("[ERROR] Mask size mismatch.")
        mask_bool = mask_arr.reshape((rows, cols)) > 0.5 #same as astype(bool), but safer in case there are some rounding issues
        meta['dtype'] = 'float32'
        meta['nodata'] = np.nan

    for b in bin_files:
        arr = read_bin(b, rows, cols, dtype)
        if mask_bool is not None:
            arr = np.where(mask_bool, arr, np.nan)
        out = outdir / (b.stem + (args.suffix or "") + ".tif")
        write_geotiff(out, arr, meta)
        print(f"[OK] {b.name} → {out}")

if __name__ == "__main__":
    main()