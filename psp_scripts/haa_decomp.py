#!/usr/bin/env python3
import argparse, json, os, sys, subprocess
from pathlib import Path

# default exe path; change if needed or use --exe/--use-psp
DEFAULT_EXE = Path.home() / "polsarpro" / "Soft" / "bin" / "data_process_sngl" / "h_a_alpha_decomposition.exe"

# map flags -> expected output filenames in PolSARpro
FLAG_OUTPUTS = {
    "fl2": ["lambda.bin"],  # eigenvalues (name may vary by build)
    "fl3": ["alpha.bin"],                                   # mean alpha (in degrees)
    "fl4": ["entropy.bin"],                                       # entropy
    "fl5": ["anisotropy.bin"],                                       # anisotropy
    "fl6": ["combination_HA.bin"],                                 # combined maps (names vary; best effort)
    "fl7": ["combination_H1mA.bin"],
    "fl8": ["combination_1mHA.bin"],
    "fl9": ["combination_1mH1mA.bin"],
}

def load_meta_from_json(folder: Path):
    mj = folder / "metadata.json"
    if not mj.exists():
        return None
    with mj.open() as f:
        m = json.load(f)
    # normalize to ints
    out = {}
    for k in ("rows","cols","fnr","fnc","ofr","ofc"):
        if k in m:
            try: out[k] = int(m[k])
            except Exception: pass
    return out

def load_meta_from_config(folder: Path):
    cfg = folder / "config.txt"
    if not cfg.exists():
        return None
    out = {"ofr": 0, "ofc": 0}  # defaults
    with cfg.open() as f:
        for line in f:
            if "=" not in line: continue
            k, v = line.split("=", 1)
            key = k.strip().lower()
            val = v.strip()
            if key in ("nlig","nrow","rows"):
                try: out["rows"] = int(val)
                except: pass
            if key in ("ncol","cols"):
                try: out["cols"] = int(val)
                except: pass
    if "rows" in out and "cols" in out:
        out["fnr"] = out["rows"]
        out["fnc"] = out["cols"]
    return out

def resolve_sizes(input_dir: Path):
    meta = load_meta_from_json(input_dir) or load_meta_from_config(input_dir)
    if not meta or "rows" not in meta or "cols" not in meta:
        raise RuntimeError(f"Could not determine rows/cols from metadata in {input_dir}")
    # defaults if absent
    meta.setdefault("ofr", 0)
    meta.setdefault("ofc", 0)
    meta.setdefault("fnr", meta["rows"])
    meta.setdefault("fnc", meta["cols"])
    return meta

def build_expected_outputs(out_dir: Path, flags: dict):
    exp = []
    for k, enabled in flags.items():
        if not enabled: continue
        for name in FLAG_OUTPUTS.get(k, []):
            exp.append(out_dir / name)
    return exp

def ran_ok(rc: int, stdout: str, stderr: str, expected_files):
    banner = "A processing error occured"
    if banner in stdout or banner in stderr:
        return False
    if rc not in (0, 1):              # PolSARpro often returns 1 on success
        return False
    missing = [p for p in expected_files if not p.exists()]
    return len(missing) == 0

def main():
    ap = argparse.ArgumentParser(description="Wrapper for PolSARpro h_a_alpha_decomposition.exe")
    ap.add_argument("-i", "--input", required=True, help="Input directory containing T3/C3 and config/metadata")
    ap.add_argument("-o", "--output", help="Output directory (default: <input>_HAA)")
    ap.add_argument("--iodf", default="T3", choices=["T3","C3","t3","c3"], help="Input-output data format")
    ap.add_argument("--nwr", type=int, default=1, help="Window size rows (Nwin Row). Use 1 for no extra filtering.")
    ap.add_argument("--nwc", type=int, default=1, help="Window size cols (Nwin Col). Use 1 for no extra filtering.")
    ap.add_argument("--ofr", type=int, help="Offset Row (default from metadata or 0)")
    ap.add_argument("--ofc", type=int, help="Offset Col (default from metadata or 0)")
    ap.add_argument("--fnr", type=int, help="Final Number of Row (default: input rows)")
    ap.add_argument("--fnc", type=int, help="Final Number of Col (default: input cols)")

    # output flags (0/1)
    ap.add_argument("-fl1", "--fl1", type=int, default=0, help="Flag Parameters (0/1)")
    ap.add_argument("-fl2", "--fl2", type=int, default=0, help="Flag Lambda (0/1)")
    ap.add_argument("-fl3", "--fl3", type=int, default=1, help="Flag Alpha (0/1)")      # on by default
    ap.add_argument("-fl4", "--fl4", type=int, default=1, help="Flag Entropy (0/1)")   # on by default
    ap.add_argument("-fl5", "--fl5", type=int, default=1, help="Flag Anisotropy (0/1)") # on by default
    ap.add_argument("-fl6", "--fl6", type=int, default=0, help="Flag Comb HA (0/1)")
    ap.add_argument("-fl7", "--fl7", type=int, default=0, help="Flag Comb H1mA (0/1)")
    ap.add_argument("-fl8", "--fl8", type=int, default=0, help="Flag Comb 1mHA (0/1)")
    ap.add_argument("-fl9", "--fl9", type=int, default=0, help="Flag Comb 1mH1mA (0/1)")

    ap.add_argument("--mask", help="Optional mask file (valid pixels)")
    ap.add_argument("--errf", help="Optional memory error file path (written by PolSARpro)")
    ap.add_argument("--overwrite", action="store_true", help="Allow writing into existing non-empty output dir")
    ap.add_argument("--use-psp", action="store_true", help="Invoke via 'psp data_process_sngl h_a_alpha_decomposition.exe'")
    ap.add_argument("--exe", help="Path to h_a_alpha_decomposition.exe (overrides default)")

    ap.add_argument("--bmp", action="store_true", help="Create BMP plots for all the chosen outputs products")
    args = ap.parse_args()

    in_dir = Path(args.input).resolve()
    if not in_dir.is_dir():
        sys.exit(f"[ERROR] not a directory: {in_dir}")

    out_dir = Path(args.output).resolve() if args.output else Path(str(in_dir) + "_HAA")
    if out_dir.exists():
        if not args.overwrite and any(out_dir.iterdir()):
            sys.exit(f"[ERROR] output exists and is not empty: {out_dir} (use --overwrite)")
    else:
        out_dir.mkdir(parents=True)

    sizes = resolve_sizes(in_dir)
    ofr = args.ofr if args.ofr is not None else sizes["ofr"]
    ofc = args.ofc if args.ofc is not None else sizes["ofc"]
    fnr = args.fnr if args.fnr is not None else sizes["fnr"]
    fnc = args.fnc if args.fnc is not None else sizes["fnc"]

    iodf = args.iodf.upper()
    flags = {f"fl{i}": getattr(args, f"fl{i}") for i in range(1, 10)}

    # Build command exactly per your binary's interface
    if args.use_psp:
        base = ["psp", "data_process_sngl", "h_a_alpha_decomposition.exe"]
    else:
        exe = Path(args.exe) if args.exe else DEFAULT_EXE
        base = [str(exe)]

    cmd = base + [
        "-id", str(in_dir),
        "-od", str(out_dir),
        "-iodf", iodf,
        "-nwr", str(max(1, args.nwr)),
        "-nwc", str(max(1, args.nwc)),
        "-ofr", str(ofr),
        "-ofc", str(ofc),
        "-fnr", str(fnr),
        "-fnc", str(fnc),
        "-fl1", str(flags["fl1"]),
        "-fl2", str(flags["fl2"]),
        "-fl3", str(flags["fl3"]),
        "-fl4", str(flags["fl4"]),
        "-fl5", str(flags["fl5"]),
        "-fl6", str(flags["fl6"]),
        "-fl7", str(flags["fl7"]),
        "-fl8", str(flags["fl8"]),
        "-fl9", str(flags["fl9"]),
    ]
    if args.mask:
        cmd += ["-mask", str(Path(args.mask).resolve())]
    if args.errf:
        cmd += ["-errf", str(Path(args.errf).resolve())]

    print("[INFO] running:", " ".join(cmd))
    cp = subprocess.run(cmd, text=True, capture_output=True)

    expected = build_expected_outputs(out_dir, flags)
    if not ran_ok(cp.returncode, cp.stdout, cp.stderr, expected):
        if cp.stdout: print(cp.stdout)
        if cp.stderr: print(cp.stderr, file=sys.stderr)
        sys.exit(f"[ERROR] H/A/α failed (rc={cp.returncode}).")

    made = [p.name for p in expected if p.exists()]
    print("[OK] H/A/α complete. Outputs:", ", ".join(made) if made else "(none requested)")

    #optional - create BMP plots
    if args.bmp:
        print('[INFO] Creating BMP images...')
    # map flags -> files to visualize
        want = []
        if args.fl3: want += ["alpha.bin"]             # add others if you like: beta/delta/gamma/epsilon/nhu
        if args.fl4: want += ["entropy.bin"]
        if args.fl5: want += ["anisotropy.bin"]
        if args.fl6: want += ["combination_HA.bin"]
        if args.fl7: want += ["combination_H1mA.bin"]
        if args.fl8: want += ["combination_1mHA.bin"]
        if args.fl9: want += ["combination_1mH1mA.bin"]

        # load rows/cols from input metadata.json/config.txt (same as before)
        rows, cols, fnr, fnc, ofr, ofc = sizes["rows"], sizes["cols"], sizes["fnr"], sizes["fnc"], sizes["ofr"], sizes["ofc"]

        bmp_exe = "/home/jpe128/polsarpro/Soft/bin/bmp_process/create_bmp_file.exe"
        for name in want:
            src = out_dir / name
            if not src.exists(): 
                continue
            dst = src.with_suffix(".bmp")
            cmd = [
                bmp_exe, "-if", str(src), "-of", str(dst),
                "-ift", "float", "-oft", "real", "-clm", "gray",
                "-nc", str(cols), "-ofr", str(ofr), "-ofc", str(ofc),
                "-fnr", str(fnr), "-fnc", str(fnc),
                "-min", "0", "-max", "1", "-mm", "1"
            ]
            print("[INFO] BMP:", " ".join(cmd))
            subprocess.run(cmd, check=False)
if __name__ == "__main__":
    main()

