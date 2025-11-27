import os
import glob
import subprocess
import matplotlib.pyplot as plt
import numpy as np
from osgeo import gdal

import isce
import isceobj


def estimate_boundary_n(phi_north, coh_north,
                        phi_south, coh_south,
                        N=400, M=400, coh_thr=0.7):
    """Return integer n such that phi_north - n*2pi = phi_south at boundary."""
    phi_n = phi_north[-N:, :M]
    phi_s = phi_south[:N, :M]

    coh_n = coh_north[-N:, :M]
    coh_s = coh_south[:N, :M]

    mask = (coh_n > coh_thr) & (coh_s > coh_thr)
    diff = np.where(mask, phi_n - phi_s, np.nan)

    med = np.nanmedian(diff)
    ratio = med / (2*np.pi)
    n = int(np.round(ratio))
    print(f"boundary diff/2pi = {ratio:.3f}, n = {n}")
    return n


def estimate_segment_offsets(phi_list, coh_list):
    """
    phi_list: [phi_s1, phi_s2, phi_s3, phi_s4]
    coh_list: [cor_s1, cor_s2, cor_s3, cor_s4]
    returns integer offsets c1..c4 (multipliers of 2pi) relative to segment 1
    """
    n12 = estimate_boundary_n(phi_list[0], coh_list[0], phi_list[1], coh_list[1])
    n23 = estimate_boundary_n(phi_list[1], coh_list[1], phi_list[2], coh_list[2])
    n34 = estimate_boundary_n(phi_list[2], coh_list[2], phi_list[3], coh_list[3])

    c1 = 0
    c2 = c1 - n12
    c3 = c2 - n23
    c4 = c3 - n34
    return [c1, c2, c3, c4]


#for reading single band products (cor, conncomp, geometry files)
def populate_array_pattern(stack_dir, pair, pattern, product_type='i', pol='hh', nr_segments = 4):
    seg_arr = []
    for s in range(nr_segments):
        seg = s+1
        if product_type.lower()=='i':
            segment_path = os.path.join(stack_dir, f's{seg}_{pol}', 'Igrams', pair)
        elif product_type.lower()=='g':
            segment_path = os.path.join(stack_dir, f's{seg}_{pol}', 'geom_reference')
        else:
            print("Enter product type: g (geometry) or i (interferogram)")
        unw_path = glob.glob(os.path.join(segment_path, pattern))
        arr = gdal.Open(unw_path[0]).ReadAsArray()[:, :]
        seg_arr.append(arr)
    return seg_arr

#for reading multiband products - typically interferograms (band=0 amplitude, band=1 phase)
def populate_array_pattern_multiband(stack_dir, pair, pattern, product_type='i', band=1, pol='hh', nr_segments = 4):
    seg_arr = []
    for s in range(nr_segments):
        seg = s+1
        if product_type.lower()=='i':
            segment_path = os.path.join(stack_dir, f's{seg}_{pol}', 'Igrams', pair)
        elif product_type.lower()=='g':
            segment_path = os.path.join(stack_dir, f's{seg}_{pol}', 'geom_reference')
        else:
            print("Enter product type: g (geometry) or i (interferogram)")
            
        unw_path = glob.glob(os.path.join(segment_path, pattern))
        arr = gdal.Open(unw_path[0]).ReadAsArray()[band, :, :]
        seg_arr.append(arr)
    return seg_arr

def write_isce_image(outfile, arr, dtype='FLOAT', scheme='BIL'):
    """
    Write arr to outfile + ISCE XML/VRT.

    scheme:
      - 'BIL' expects file order (length, bands, width)
      - 'BSQ' expects file order (bands, length, width)
    """
    if arr.ndim == 2:
        bands = 1
        length, width = arr.shape
        arr_out = arr.astype(np.float32)

    elif arr.ndim == 3:
        bands, length, width = arr.shape

        #dumping bytes to disk happens from the last axis to the first axis
        #BSQ width, lenght of band 1; width length of band2
        #if you need band-interleaved-by-line (BIL), bands needs to be the middle axis. 
        if scheme.upper() == 'BIL':
            # convert (bands, length, width) -> (length, bands, width)
            arr_out = np.transpose(arr, (1, 0, 2)).astype(np.float32)
        elif scheme.upper() == 'BSQ':
            # keep (bands, length, width)
            arr_out = arr.astype(np.float32)
        else:
            raise ValueError("scheme must be 'BIL' or 'BSQ'")
    else:
        raise ValueError("arr must be 2D or 3D")

    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    arr_out.tofile(outfile)

    img = isceobj.Image.createImage()
    img.setFilename(outfile)
    img.setWidth(width)
    img.setLength(length)
    img.bands = bands
    img.scheme = scheme.upper()
    img.dataType = dtype
    img.setAccessMode('read')
    img.renderHdr() #writes xml
    img.renderVRT() #writes vrt


pairs = ['20170606_20170813', '20170606_20171009', '20170813_20171009']
pols = ['hh', 'vv', 'hv']
nr_segments = 4
flightline = 'dhorse'
dir_stack = f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/{flightline}_stack'

multiband_ifg_products = ['filt_*.unw']
singleband_ifg_products = ['filt_*.cor', 'filt_*.conncomp']

singleband_geometry_products = ['hgt.rdr', 'lat.rdr', 'lon.rdr', 'shadowMask.rdr']
multiband_geometry_products = ['los.rdr']

for pol in pols:
    output_dir = os.path.join(dir_stack, f'mosaic_{pol}')
    ######geometry products don't depend on pair
    hgt = populate_array_pattern(dir_stack, None, 'hgt.rdr', product_type='g', pol=pol, nr_segments=nr_segments)
    mosaic_hgt = np.vstack(hgt)
    write_isce_image(os.path.join(output_dir, 'geom_reference', 'hgt.rdr'), arr=mosaic_hgt)

    lat = populate_array_pattern(dir_stack, None, 'lat.rdr', product_type='g', pol=pol, nr_segments=nr_segments)
    mosaic_lat = np.vstack(lat)
    write_isce_image(os.path.join(output_dir, 'geom_reference', 'lat.rdr'), arr=mosaic_lat)

    lon = populate_array_pattern(dir_stack, None, 'lon.rdr', product_type='g', pol=pol, nr_segments=nr_segments)
    mosaic_lon = np.vstack(lon)
    write_isce_image(os.path.join(output_dir, 'geom_reference', 'lon.rdr'), arr=mosaic_lon)

    shadow = populate_array_pattern(dir_stack, None, 'shadowMask.rdr', product_type='g', pol=pol, nr_segments=nr_segments)
    mosaic_shadow = np.vstack(shadow)
    write_isce_image(os.path.join(output_dir, 'geom_reference', 'shadowMask.rdr'), arr=mosaic_shadow)
    #multiband!
    los = populate_array_pattern_multiband(dir_stack, None, pattern='los.rdr', band=[0,1], product_type='g', pol='hh', nr_segments=nr_segments)
    mosaic_los = np.concatenate(los, axis=1)
    write_isce_image(os.path.join(output_dir, 'geom_reference', 'los.rdr'), arr=mosaic_los)
    
    for pair in pairs:
        
        #first, fix the two-band interferogram 
        #MintPy expect .unw product two have two bands
        #load amplitude (band 0), vstack
        #load phase, correct for 2pi, vstack
        #put back in (2, M, N), call write_isce...()

        phi_list = populate_array_pattern_multiband(dir_stack, pair=pair,band=1, pattern='filt_*.unw', product_type='i', pol=pol, nr_segments=nr_segments)
        int_amp_list = populate_array_pattern_multiband(dir_stack, pair=pair,band=0, pattern='filt_*.unw', product_type='i', pol=pol, nr_segments=nr_segments)
        coh_list = populate_array_pattern(dir_stack, pair=pair, pattern='filt_*.cor', product_type='i', pol=pol, nr_segments=nr_segments) #needed for masking, use later

        c = estimate_segment_offsets(phi_list, coh_list)
        print("segment 2pi multipliers:", c)

        phi_corr = [phi - ci * 2*np.pi for phi, ci in zip(phi_list, c)]
        mosaic_unw = np.vstack(phi_corr)
        mosaic_int_amp = np.vstack(int_amp_list)
        ######masking the garbage fill on the right in each array
        #### go with amplitude-based masking, where it's really close to 0 -> NaN
        mask = np.where(np.isclose(mosaic_int_amp, 0.0, atol=1e-3), False, True)
        mosaic_unw_masked = np.where(mask, mosaic_unw, np.nan)
        mosaic_amp_masked = np.where(mask, mosaic_int_amp, np.nan)

        #twoband_unw = np.stack([mosaic_int_amp, mosaic_unw])
        twoband_unw = np.stack([mosaic_amp_masked, mosaic_unw_masked])
        #write unwrapped phase product
        write_isce_image(os.path.join(output_dir, 'Igrams', pair, f'filt_{pair}_snaphu.unw'), arr=twoband_unw)
        #write coherence product
        mosaic_coh = np.vstack(coh_list)
        write_isce_image(os.path.join(output_dir, 'Igrams', pair, f'filt_{pair}.cor'), arr=mosaic_coh)
        #conncomp
        conncomp = populate_array_pattern(dir_stack, pair, 'filt_*.conncomp', product_type='i', pol=pol, nr_segments=nr_segments)
        mosaic_conncomp = np.vstack(conncomp)
        write_isce_image(os.path.join(output_dir, 'Igrams', pair, f'filt_{pair}_snaphu.unw.conncomp'), arr=mosaic_conncomp)

        