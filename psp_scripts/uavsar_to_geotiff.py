import os
from os.path import exists, basename, join, isfile
from glob import glob
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine
from rasterio.crs import CRS
import sys
import argparse


def get_encapsulated(str_line, encapsulator):
    """
    Returns items found in the encapsulator, useful for finding units
    Originally written by Micah J. Amended for uavsar_pytools by Zach Keskinen.
    Args:
        str_line: String that has encapusulated info we want removed
        encapsulator: string of characters encapusulating info to be removed
    Returns:
        result: list of strings found inside anything between encapsulators
    e.g.
        line = 'density (kg/m^3), temperature (C)'
        ['kg/m^3', 'C'] = get_encapsulated(line, '()')
    """

    result = []

    if len(encapsulator) > 2:
        raise ValueError('encapsulator can only be 1 or 2 chars long!')

    elif len(encapsulator) == 2:
        lcap = encapsulator[0]
        rcap = encapsulator[1]

    else:
        lcap = rcap = encapsulator

    # Split on the lcap
    if lcap in str_line:
        for i, val in enumerate(str_line.split(lcap)):
            # The first one will always be before our encapsulated
            if i != 0:
                if lcap != rcap:
                    result.append(val[0:val.index(rcap)])
                else:
                    result.append(val)

    return result

def read_annotation(ann_file):
    """
    .ann files describe the INSAR data. Use this function to read all that
    information in and return it as a dictionary
    Originally written by Micah J. Amended for uavsar_pytools by Zach Keskinen.

    Expected format:
    `DEM Original Pixel spacing (arcsec) = 1`
    Where this is interpretted as:
    `key (units) = [value]`
    Then stored in the dictionary as:
    `data[key] = {'value':value, 'units':units}`
    values that are found to be numeric and have a decimal are converted to a
    float otherwise numeric data is cast as integers. Everything else is left
    as strings.
    Args:
        ann_file: path to UAVSAR annotation file
    Returns:
        data: Dictionary containing a dictionary for each entry with keys
              for value, units and comments
    """

    with open(ann_file) as fp:
        lines = fp.readlines()
        fp.close()
    data = {}

    # loop through the data and parse
    for line in lines:

        # Filter out all comments and remove any line returns
        info = line.strip().split(';')
        comment = info[-1].strip().lower()
        info = info[0]
        # ignore empty strings
        if info and "=" in info:
            d = info.split('=')
            name, value = d[0], d[1]
            # Clean up tabs, spaces and line returns
            key = name.split('(')[0].strip().lower()
            units = get_encapsulated(name, '()')
            if not units:
                units = None
            else:
                units = units[0]

            value = value.strip()

            # Cast the values that can be to numbers ###
            if value.strip('-').replace('.', '').isnumeric():
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)

            # Assign each entry as a dictionary with value and units
            data[key] = {'value': value, 'units': units, 'comment': comment}

    # Convert times to datetimes
    if 'start time of acquistion for pass 1' in data.keys():
        for pass_num in ['1', '2']:
            for timing in ['start', 'stop']:
                key = f'{timing} time of acquisition for pass {pass_num}'
                dt = pd.to_datetime(data[key]['value'])
                data[key]['value'] = dt
    elif 'start time of acquisition' in data.keys():
        for timing in ['start', 'stop']:
                key = f'{timing} time of acquisition'
                dt = pd.to_datetime(data[key]['value'])
                data[key]['value'] = dt

    return data

def grd_tiff_convert(in_fp, out_dir, ann_fp = None, overwrite = 'user', PBAND=False, return_values=False):
    """
    Converts a single binary image either polsar or insar to geotiff.
    See: https://uavsar.jpl.nasa.gov/science/documents/polsar-format.html for polsar
    and: https://uavsar.jpl.nasa.gov/science/documents/rpi-format.html for insar
    and: https://uavsar.jpl.nasa.gov/science/documents/stack-format.html for SLC stacks.
    Originally written by Micah J. Amended for uavsar_pytools by Zach Keskinen.

    Args:
        in_fp (string): path to input binary file
        out_dir (string): directory to save geotiff in
        ann_fp (string): path to UAVSAR annotation file
    """

    out_fp = join(out_dir, basename(in_fp)) + '.tiff'

    # Determine type of image
    if isfile(out_dir):
        raise Exception('Provide filepath not the directory.')

    if not exists(in_fp):
        raise Exception(f'Input file path: {in_fp} does not exist.')

    exts = basename(in_fp).split('.')[1:]
    if len(exts) == 2:
        ext = exts[1]
        type = exts[0]
    elif len(exts) == 1:
        type = ext = exts[0]
    else:
        raise ValueError('Unable to parse extensions')
    
    # Find annotation file in same directory if no user given one
    if not ann_fp:
        if ext == 'grd' or ext == 'slc':
            ann_fp = in_fp.replace(f'.{type}', '').replace(f'.{ext}', '.ann')
        else:
            ann_fp = in_fp.replace(f'.{ext}', '.ann')
        if not exists(ann_fp):
            search_base = '_'.join(basename(in_fp).split('.')[0].split('_')[:4])
            search_full = os.path.join(os.path.dirname(in_fp), f'{search_base}*.ann')
            ann_search = glob(search_full)
            if len(ann_search) == 1:
                ann_fp = ann_search[0]
            else:
                raise Exception('No ann file found in directory. Please specify ann filepath.')
        else:
            print(f'No annotation file path specificed. Using {ann_fp}.')

    # Check for compatible extensions
    if type == 'zip':
        raise Exception('Can not convert zipped directories. Unzip first.')
    if type == 'dat' or type == 'kmz' or type == 'kml' or type == 'png' or type == 'tif':
        raise Exception(f'Can not handle {type} products')
    if type == 'ann':
        raise Exception(f'Can not convert annotation files.')

    # Check for slant range files and ancillary files
    anc = None
    if type == 'slope' or type == 'inc':
        anc = True
    # Check if file already exists and for overwriting
    ans = 'N'
    #this doesn't work for slope, because the out_fp has east and north in the name, so exists(out_fp) is always false
    #can't be bothered to add another if statement just for this...
    if exists(out_fp):
            if overwrite == True:
                ans = 'y'
            elif overwrite == False:
                ans = 'n'
            else:
                ans = input(f'\nWARNING! You are about overwrite {out_fp}!.  '
                            f'\nPress Y to continue and any other key to abort: ').lower()
            if ans == 'y':
                os.remove(out_fp)
    if ans == 'n':
        print(f'Skipping {os.path.basename(out_fp)}...\n')
        return 
    
    if ans == 'y' or exists(out_fp) == False:

        # Read in annotation file
        desc = read_annotation(ann_fp)
        #pd.DataFrame.from_dict(desc).to_csv('../data/test.csv')
        if 'start time of acquisition for pass 1' in desc.keys():
            mode = 'insar'
        else:
            mode = 'polsar'
        #print(f'Working with {mode} file {os.path.basename(in_fp)}')

        # Determine the correct file typing for searching our data dictionary
        if not anc:
            if mode == 'polsar':
                if type == 'hgt':
                    search = type
                else:
                    if PBAND:
                        polarization = basename(in_fp).split('_')[6][-4:]
                    else:
                        polarization = basename(in_fp).split('_')[5][-4:]
                    if polarization == 'HHHH' or polarization == 'HVHV' or polarization == 'VVVV':
                            search = f'{type}_pwr'
                    else:
                        search = f'{type}_phase'
                    type = polarization

            elif mode == 'insar':
                if ext == 'grd':
                    if type == 'int':
                        search = f'grd_phs'
                    else:
                        search = 'grd'
                else:
                    if type == 'int':
                        search = 'slt_phs'
                    else:
                        search = 'slt'
        else:
            #search = type
            search = 'hgt'


        # Pull the appropriate values from our annotation dictionary
        nrow = desc[f'{search}.set_rows']['value']
        ncol = desc[f'{search}.set_cols']['value']

        if ext == 'grd' or anc:
            # Ground projected images
            # Delta latitude and longitude
            dlat = desc[f'{search}.row_mult']['value']
            dlon = desc[f'{search}.col_mult']['value']
            # Upper left corner coordinates
            lat1 = desc[f'{search}.row_addr']['value']
            lon1 = desc[f'{search}.col_addr']['value']

            # Lat1/lon1 are already the center so for geotiff were good to go.
            t = Affine.translation(float(lon1), float(lat1))* Affine.scale(float(dlon), float(dlat))

            # Build the transform and CRS
            crs = CRS.from_user_input("EPSG:4326")
        # Get data type specific data
        bytes = desc[f'{search}.val_size']['value']
        endian = desc['val_endi']['value']

        # Set up datatypes
        com_des = desc[f'{search}.val_frmt']['value']
        com = False
        if 'COMPLEX' in com_des:
            com = True
        if com:
            dtype = np.complex64
        else:
            dtype = np.float32
        # Read in binary data
        z = np.fromfile(in_fp, dtype = dtype)

        # Reshape it to match what the text file says the image is
        if type == 'slope':
            z[z==-10000]= np.nan
            slopes = {}
            slopes['east'] = z[::2].reshape(nrow, ncol)
            slopes['north'] = z[1::2].reshape(nrow, ncol)
        else:
            slopes = None
            z = z.reshape(nrow, ncol)


        # Change zeros and -10,000 to nans based on documentation.
        if com:
            z[z== 0 + 0*1j] = np.nan + np.nan * 1j
        else:
            z[z==0]= np.nan
            z[z==-10000]= np.nan

        if slopes:
            slope_fps = []
            for direction, array in slopes.items():
                slope_fp = out_fp.replace('.tiff',f'.{direction}.tiff')
                dataset = rasterio.open(
                slope_fp,
                'w+',
                driver='GTiff',
                height=array.shape[0],
                width=array.shape[1],
                count=1,
                dtype=dtype,
                crs=crs,
                transform=t,)
                # Write out the data
                print(f'writing out slopes tiff file {os.path.basename(out_fp)}')
                dataset.write(array, 1)

                dataset.close()
                slope_fps.append(slope_fp)
            return desc, z, type, slope_fps
        else:

            if ext == 'grd' or anc:
                dataset = rasterio.open(
                    out_fp,
                    'w+',
                    driver='GTiff',
                    height=z.shape[0],
                    width=z.shape[1],
                    count=1,
                    dtype=dtype,
                    crs=crs,
                    transform=t,)
            else:
                dataset = rasterio.open(
                    out_fp,
                    'w+',
                    driver='GTiff',
                    height=z.shape[0],
                    width=z.shape[1],
                    count=1,
                    dtype=dtype,)
            # Write out the data
            print(f'writing out tiff file {os.path.basename(out_fp)}')
            dataset.write(z, 1)

            dataset.close()
        if return_values:
            return desc, z, type, out_fp
        else: 
            return 0

def convert_full_folder(input_dir, output_dir, overwrite='user', PBAND=False):
    EXT = {".grd", ".slc", ".inc", ".hgt", ".int"} #".slope"
    files = [
        os.path.join(input_dir, f) for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f))
        and os.path.splitext(f)[1].lower() in EXT]
    
    ann_file = glob(os.path.join(input_dir, '*.ann'))[0]
    print(f'Converting files in {input_dir} \n')
    for f in files:
        grd_tiff_convert(in_fp=f, out_dir=output_dir, ann_fp=ann_file, overwrite=overwrite, PBAND=PBAND, return_values=False)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: convert_to_geotiff.py -i <UAVSAR_GRD_input_folder> -o <T3_matrix_output_folder>")
        print("Additional arguments that can be specified: overwrite (bool), PBAND (bool)")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-dir', help="Input directory containing UAVSAR binary files")
    parser.add_argument('-o', '--output-dir', help="Output directory for storing the converted GeoTiff files")
    parser.add_argument("--overwrite", action="store_true", help="Allow writing into existing non-empty output dir")
    parser.add_argument("--PBAND", action='store_true', help="If this is a P-band dataset")
    args = parser.parse_args()

    if not args.input_dir:
        sys.exit('No input folder given.')
    else:
        input_dir = os.path.abspath(args.input_dir)
        if not os.path.isdir(input_dir):
            sys.exit(f'Folder not found: {input_dir}')

    if not args.output_dir:
        output_dir = os.path.join(input_dir, 'tiff')
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
            print(f'No output folder given, creating one in {output_dir}')
        
    else:
        output_dir = os.path.abspath(args.output_dir)
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
        elif args.overwrite:
            print(f'Overwriting the contents of {output_dir}')
        else:
            sys.exit('Output folder already exists and overwrite is set to False, exiting...')
    
    if args.overwrite:
        overwrite = args.overwrite
    else:
        overwrite = False
    
    if args.PBAND:
        PBAND = args.PBAND
    else:
        PBAND = False

    print(f'Data will be saved to {output_dir}')
    convert_full_folder(input_dir=input_dir, output_dir=output_dir, overwrite=overwrite, PBAND=PBAND)
    print('Conversion done.')


###################
if __name__ == '__main__':
    main()
