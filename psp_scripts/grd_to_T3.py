import numpy as np
import os
import subprocess
import glob
import re
import sys
import argparse
import json

def find_ann(folder):
    '''finds annotation file in the given folder, returns absolute path to the .ann file'''
    ann_files = list(glob.glob(os.path.join(folder, '*.ann')))
    if not ann_files:
        raise FileNotFoundError(f'No annotation file found in {folder}.')
    if len(ann_files)>1:
        print(f'Too many annotation files found, using {ann_files[0]}.')
    ann_file_path = os.path.abspath(ann_files[0])
    return ann_file_path

def find_polarizations(folder):
    pols = ['HHHH', 'HHHV', 'HHVV', 'HVHV', 'HVVV', 'VVVV']
    input_file_paths = {}
    for pol in pols:
        pol_path = list(glob.glob(os.path.join(folder, f'*{pol}*.grd')))
        if not pol_path:
            raise FileNotFoundError(f'No file found for the {pol} matrix element.')
        else:
            input_file_paths[f'{pol}'] = pol_path
    return input_file_paths

def read_rows_cols(ann_path):
    rows = cols = None
    with open(ann_path) as f:
        for line in f:
            # look for keys like "grd_pwr.set_rows = 3750"
            if re.search(r"grd_pwr\.set_rows", line, re.IGNORECASE):
                rows = int(re.findall(r"\d+", line)[0]) #\d+ means any number of digits 0 to 9
            elif re.search(r"grd_pwr\.set_cols", line, re.IGNORECASE):
                cols = int(re.findall(r"\d+", line)[0])
            if rows and cols:
                break
    if not rows or not cols:
        raise ValueError(f"Could not find grd_pwr.set_rows/cols in {ann_path}")
    return rows, cols

def run_psp_grdToT3(input_folder, output_folder, odf='T3', ofr=0, ofc=0, nlr=1, nlc=1, ssr=1, ssc=1):
    #annotation file 
    hf = find_ann(input_folder)
    #pol channels files
    grd = find_polarizations(input_folder)
    rows, cols = read_rows_cols(hf)
    #initial and final number of rows (the program handles the final number by itself, I think, so just pass the same value)
    inr = fnr = rows
    inc = fnc = cols
    #path to the executable file
    PATH_TO_EXE = os.path.join('/home/jpe128/polsarpro/Soft/bin/data_import','uavsar_convert_MLC.exe')
    cmd = [
        str(PATH_TO_EXE),
        "-hf", str(hf),
        "-if1", str(grd["HHHH"][0]),
        "-if2", str(grd["HHHV"][0]),
        "-if3", str(grd["HHVV"][0]),
        "-if4", str(grd["HVHV"][0]),
        "-if5", str(grd["HVVV"][0]),
        "-if6", str(grd["VVVV"][0]),
        "-od", str(output_folder),
        "-odf", str(odf), #output format
        "-inr", str(inr), #initial number of rows/cols
        "-inc", str(inc),
        "-ofr", str(ofr), #offsets rows/cols
        "-ofc", str(ofc),
        "-fnr", str(fnr), #final number of rows/cols
        "-fnc", str(fnc),
        "-nlr", str(nlr), #number of looks
        "-nlc", str(nlc),
        "-ssr", str(ssr), #subsampling
        "-ssc", str(ssc), 
    ]
    print("[INFO] Running:", " ".join(cmd))
    subprocess.run(cmd, check=False)

    meta = {
    "ann_file_orig" : hf,
    "rows": inr,
    "cols": inc,
    "looks_row": nlr,
    "looks_col": nlc,
    "subsampling_row": ssr,
    "subsampling_col": ssc,
    "ofr": ofr,
    "ofc": ofc,
    "fnr": fnr,
    "fnc": fnc,
    "output_matrix": odf,
    }
    meta_path = os.path.join(output_folder, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[INFO] wrote metadata to {meta_path}")



def main():
    if len(sys.argv) < 2:
        print(f"Usage: grd_to_T3.py -i <UAVSAR_GRD_input_folder> -o <T3_matrix_output_folder>")
        print("Additional arguments that can be specified: number of looks nlr (int), nlc (int); output matrix type odf ('C3' or 'T3')")
        sys.exit(1)

    
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="Path to the input folder")
    parser.add_argument("-o", "--output", help="Path to the output folder")
    parser.add_argument("-odf", "--output-matrix", default='T3', help="Output matrix type, C3 or T3 (default)")
    parser.add_argument("-nlr", "--Nlooks-rows", default=1, help='Number of looks - rows')
    parser.add_argument("-nlc", "--Nlooks-columns", default=1, help='Number of looks - columns')

    parser.add_argument("--overwrite", action="store_false", help="Allow writing into existing non-empty output dir")

    args = parser.parse_args()
    if not args.input:
        sys.exit('No input folder given.')
    else:
        input_folder = os.path.abspath(args.input)
        if not os.path.isdir(input_folder):
            sys.exit(f'Folder not found: {input_folder}')

    if not args.output:
        output_folder = os.path.join(input_folder, 'T3')
        if not os.path.isdir(output_folder):
            os.mkdir(output_folder)
            print('No output folder given, creating one...')
        
    else:
        output_folder = os.path.abspath(args.output)
        if not os.path.isdir(output_folder):
            os.mkdir(output_folder)
        elif args.overwrite:
            print(f'Overwriting the contents of {output_folder}')
        else:
            sys.exit('Output folder already exists and overwrite is set to False, exiting...')

    if args.output_matrix:
        odf = args.output_matrix
    else:
        odf = 'T3'
    
    if args.Nlooks_rows:
        nlr = args.Nlooks_rows
    else:
        nlr = 1
    if args.Nlooks_columns:
        nlc= args.Nlooks_columns
    else:
        nlc = 1

    run_psp_grdToT3(input_folder=input_folder, output_folder=output_folder, odf=odf, nlr=nlr, nlc=nlc)
   
    

    
if __name__ == "__main__":
    main()