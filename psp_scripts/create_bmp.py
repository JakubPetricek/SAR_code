import os
import json
import sys
import subprocess
import argparse

def main():
    cwd = os.getcwd()

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="Path to the input file")
    parser.add_argument("-o", "--output", help="Path to the output file")
    parser.add_argument("-ift", "--input-format", default="float", help="Input data format (cmplx, float, int), default float")
    parser.add_argument("-oft", "--output-format", default="real", help="Output data format (real, imag, mod, pha, db10, db20), default real")
    parser.add_argument("-m", "--meta", default=os.path.join(cwd, 'metadata.json'), help="Path to the metadata file")
    parser.add_argument("-clm", "--colormap", default='gray', help="Colormap for the BMP image (gray, grayrev, jet, jetinv, jetrev, hsv, hsvinv, hsvrev), default gray")
    parser.add_argument("-min", "--min", default=0, help="Minimum pixel value (will be calculated anyway if mm=1)")
    parser.add_argument("-max", "--max", default=1, help="Maximum pixel value (will be calculated anyway if mm=1)")
    parser.add_argument("-mm", "--min-max", default=1, help="Min-max determination (0,1,2,3), default 1")

    parser.add_argument("--overwrite", action="store_true", help="Allow writing into existing non-empty output dir")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        sys.exit("No input file found")

    meta_file = args.meta
    if not os.path.exists(meta_file):
        sys.exit("No metadata file found")

    with open(meta_file) as f:
        meta = json.load(f)

    rows, cols = meta["rows"], meta["cols"]
    fnr, fnc = meta["fnr"], meta["fnc"]
    ofr, ofc = meta["ofr"], meta["ofc"]

    if not args.output:
        output = os.path.splitext(args.input)[0] + ".bmp"
    else:
        output = args.output

    cmd = [
            "/home/jpe128/polsarpro/Soft/bin/bmp_process/create_bmp_file.exe",
            "-if", str(args.input),
            "-of", str(output),
            "-ift", args.input_format, "-oft", args.output_format, "-clm", args.colormap,
            "-nc", str(cols),
            "-ofr", str(ofr), "-ofc", str(ofc),
            "-fnr", str(fnr), "-fnc", str(fnc),
            "-min", str(args.min), "-max", str(args.max),
            "-mm", str(args.min_max)
        ]
    print("[INFO] Running:", " ".join(cmd))
    subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()