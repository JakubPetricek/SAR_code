import os
import io
import zipfile
import numpy as np
import requests
from osgeo import gdal


def write_aster_wbd_raw_xml(mosa_shape, latMin, latMax, lonMin, lonMax, outputFile):
    """
    Write ASTER water mask mosaic to ISCE-style .wbd + .xml.

    mosa: 2D np.array (int8) with values {0, -1, -2}
    outputFile: path WITHOUT extension (e.g. /path/wbdAster_Lat.._Lon..)
    """
    import numpy as np

    nlines, nsamps = mosa_shape


    ddeg = 1.0 / 3600.0

    # coordinate1 (width, x / lon)
    x_start = float(lonMin)
    x_delta = ddeg
    x_size  = nsamps
    x_end   = x_start + x_delta * (x_size - 1)

    # coordinate2 (length, y / lat), decreasing with line index
    y_start = float(latMax)
    y_delta = -ddeg
    y_size  = nlines
    y_end   = y_start + y_delta * (y_size - 1)

    basename = os.path.basename(outputFile)
    vrt_name = basename + '.wbd.vrt'
    wbd_name = basename + '.wbd'

    xml = f"""<image_name>
    <property name="access_mode">
        <value>read</value>
        <doc>Image access mode.</doc>
    </property>
    <property name="byte_order">
        <value>l</value>
        <doc>Endianness of the image.</doc>
    </property>
    <component name="coordinate1">
        <factorymodule>isceobj.Image</factorymodule>
        <factoryname>createCoordinate</factoryname>
        <doc>First coordinate of a 2D image (width).</doc>
        <property name="delta">
            <value>{x_delta}</value>
            <doc>Coordinate quantization.</doc>
        </property>
        <property name="endingvalue">
            <value>{x_end}</value>
            <doc>Ending value of the coordinate.</doc>
        </property>
        <property name="family">
            <value>imagecoordinate</value>
            <doc>Instance family name</doc>
        </property>
        <property name="name">
            <value>imagecoordinate_name</value>
            <doc>Instance name</doc>
        </property>
        <property name="size">
            <value>{x_size}</value>
            <doc>Coordinate size.</doc>
        </property>
        <property name="startingvalue">
            <value>{x_start}</value>
            <doc>Starting value of the coordinate.</doc>
        </property>
    </component>
    <component name="coordinate2">
        <factorymodule>isceobj.Image</factorymodule>
        <factoryname>createCoordinate</factoryname>
        <doc>Second coordinate of a 2D image (length).</doc>
        <property name="delta">
            <value>{y_delta}</value>
            <doc>Coordinate quantization.</doc>
        </property>
        <property name="endingvalue">
            <value>{y_end}</value>
            <doc>Ending value of the coordinate.</doc>
        </property>
        <property name="family">
            <value>imagecoordinate</value>
            <doc>Instance family name</doc>
        </property>
        <property name="name">
            <value>imagecoordinate_name</value>
            <doc>Instance name</doc>
        </property>
        <property name="size">
            <value>{y_size}</value>
            <doc>Coordinate size.</doc>
        </property>
        <property name="startingvalue">
            <value>{y_start}</value>
            <doc>Starting value of the coordinate.</doc>
        </property>
    </component>
    <property name="data_type">
        <value>BYTE</value>
        <doc>Image data type.</doc>
    </property>
    <property name="extra_file_name">
        <value>{vrt_name}</value>
        <doc>For example name of vrt metadata.</doc>
    </property>
    <property name="family">
        <value>image</value>
        <doc>Instance family name</doc>
    </property>
    <property name="file_name">
        <value>{wbd_name}</value>
        <doc>Name of the image file.</doc>
    </property>
    <property name="length">
        <value>{y_size}</value>
        <doc>Image length</doc>
    </property>
    <property name="name">
        <value>image_name</value>
        <doc>Instance name</doc>
    </property>
    <property name="number_bands">
        <value>1</value>
        <doc>Number of image bands.</doc>
    </property>
    <property name="scheme">
        <value>BIP</value>
        <doc>Interleaving scheme of the image.</doc>
    </property>
    <property name="width">
        <value>{x_size}</value>
        <doc>Image width</doc>
    </property>
    <property name="xmax">
        <value>{x_end}</value>
        <doc>Maximum range value</doc>
    </property>
    <property name="xmin">
        <value>{x_start}</value>
        <doc>Minimum range value</doc>
    </property>
</image_name>
"""
    with open(outputFile + '.xml', 'w') as f:
        f.write(xml)


def write_aster_wbd_vrt(latMin, latMax, lonMin, lonMax, mosa_shape, outputFile):
    """
    Create a GDAL VRT next to the .wbd, matching ISCE's SWBD style.
    """
    nlines, nsamps = mosa_shape
    ddeg = 1.0 / 3600.0

    basename = os.path.basename(outputFile)
    wbd_name = basename + '.wbd'
    vrtFile = outputFile + '.wbd.vrt'

    vrt = f"""<VRTDataset rasterXSize="{nsamps}" rasterYSize="{nlines}">
    <SRS>EPSG:4326</SRS>
    <GeoTransform>{lonMin}, {ddeg}, 0.0, 0, 0.0, {-ddeg}</GeoTransform>
    <VRTRasterBand dataType="Byte" band="1" subClass="VRTRawRasterBand">
        <SourceFilename relativeToVRT="1">{wbd_name}</SourceFilename>
        <ByteOrder>LSB</ByteOrder>
        <ImageOffset>0</ImageOffset>
        <PixelOffset>1</PixelOffset>
        <LineOffset>{nsamps}</LineOffset>
    </VRTRasterBand>
    </VRTDataset>
"""
    with open(vrtFile, 'w') as f:
        f.write(vrt)

    return vrtFile
def tile_name(lat, lon):
        # lat, lon are integer degrees of SW corner
        lat_hem = 'N' if lat >= 0 else 'S'
        lon_hem = 'E' if lon >= 0 else 'W'
        
        tile = f"{lat_hem}{abs(lat):02d}{lon_hem}{abs(lon):03d}"
        print(tile)
        return tile

def download_wbd_aster_test(s, n, w, e, base_url=None, date='2000.03.01'):
    """
    Download and mosaic ASTER Global Water Body Dataset (ASTWBD) tiles.

    Output encoding matches ISCE's original WBD convention:
        0  -> land
       -1  -> water
       -2  -> no data

    Parameters
    ----------
    s, n, w, e : float
        South, North, West, East bounds in degrees.
        (Same semantics as original download_wbd.)
    base_url : str, optional
        Override base URL if needed.
        Default: ASTWBD.001 collection for given date.
    date : str, optional
        Date folder in ASTER WBD archive, e.g. '2000.03.01'.

    Returns
    -------
    outputFile : str
        Path to mosaicked water body file (without .xml),
        consistent with ISCE DemImage conventions.

    xml

    vrt
    """

    # ---------------------------------------------------------------------
    # 1. Setup
    # ---------------------------------------------------------------------
    latMin = int(np.floor(s))
    latMax = int(np.ceil(n))
    lonMin = int(np.floor(w))
    lonMax = int(np.ceil(e))

    if base_url is None:
        base_url = f"https://e4ftl01.cr.usgs.gov/ASTT/ASTWBD.001/{date}/"

    # Output name similar to original sw.defaultName(...)
    # e.g. wbdLat{latMin}_{latMax}_Lon{lonMin}_{lonMax}.wbd
    outdir = os.getcwd()
    outputFile = os.path.join(
        outdir,
        f"wbdAster_Lat{latMin}_{latMax}_Lon{lonMin}_{lonMax}.wbd"
    )
    '''
    if os.path.exists(outputFile) and os.path.exists(outputFile + '.xml'):
        print(f'ASTER WBD file: {outputFile}')
        print('exists, do not download and mosaic')
        return outputFile
    '''
    # ASTER WBD resolution: 1 arc-second, 
    ddeg = 1.0 / 3600
    nlines = int((latMax - latMin) / ddeg)
    nsamps = int((lonMax - lonMin) / ddeg)

    # Initialize with -2 (no data)
    mosa = np.full((nlines, nsamps), -2, dtype=np.int8)

    # ---------------------------------------------------------------------
    # 2. Loop over tiles: download, unzip, read, insert into mosaic
    # ---------------------------------------------------------------------
    

    for tlat in range(latMin, latMax):
        for tlon in range(lonMin, lonMax):
            tname = tile_name(tlat, tlon)
            zip_url = f"{base_url}ASTWBDV001_{tname}.zip"
            print(f"Fetching {zip_url}")

            try:
                r = requests.get(zip_url, timeout=60)
                if r.status_code != 200:
                    print(f"  -> missing tile {tname}, skipping")
                    continue
            except Exception as err:
                print(f"  -> error downloading {tname}: {err}")
                continue

            # Extract in-memory
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                tif_name = f"ASTWBDV001_{tname}_att.tif"
                if tif_name not in z.namelist():
                    print(f"  -> {tif_name} not in archive for {tname}, skipping")
                    continue
                tif_bytes = z.read(tif_name)
         
            # Write temp GeoTIFF
            tmp_tif = f"tmp_{tname}_att.tif"
           
            with open(tmp_tif, 'wb') as f:
                f.write(tif_bytes)

            # Read tile
            ds = gdal.Open(tmp_tif, gdal.GA_ReadOnly)

           
            if ds is None:
                print(f"  -> failed to open {tmp_tif}")
                #os.remove(tmp_tif)
                continue

            arr = ds.GetRasterBand(1).ReadAsArray().astype(np.int16)

            # drop last row/col to avoid overlap: 3601 -> 3600
            arr = arr[0:3600, 0:3600]

            # map to ISCE codes
            out = np.full(arr.shape, -2, dtype=np.int8)
            out[arr == 0] = 0                           # land
            out[(arr >= 1) & (arr <= 3)] = -1           # water

            gt = ds.GetGeoTransform()
            x0, dx, _, y0, _, dy = gt
            # expect dx = 1/3600, dy = -1/3600
            # y0 is north edge (tlat+1), x0 is west edge (tlon)

            # where does this tile's top-left go in mosaic?
            row_off = int(round((latMax - y0) / ddeg))
            col_off = int(round((x0 - lonMin) / ddeg))

            h, w = out.shape
            r0, r1 = row_off, row_off + h
            c0, c1 = col_off, col_off + w

            # clip to mosaic bounds
            if r0 < 0: r0 = 0
            if c0 < 0: c0 = 0
            if r1 > nlines: r1 = nlines
            if c1 > nsamps: c1 = nsamps

            mosa[r0:r1, c0:c1] = out[0:(r1-r0), 0:(c1-c0)]

            ds = None
            os.remove(tmp_tif)
    

     # ----------------- write .wbd raw -----------------
    mosa.tofile(outputFile)
    print(f'Created ASTER WBD mosaic: {outputFile}')

    write_aster_wbd_raw_xml(mosa.shape, latMin, latMax, lonMin, lonMax, outputFile)
    write_aster_wbd_vrt(latMin, latMax, lonMin, lonMax, mosa.shape, outputFile)

    print("Done. WBD:", outputFile + ".wbd")
    print("XML:", outputFile + ".wbd.xml")
    print("VRT:", outputFile + ".wbd.vrt")

    

'''

usage: 

download_wbd_aster(68, 71, -150, -146)

!geocode.py wbdAster_Lat68_71_Lon-150_-146.wbd -o waterBody.rdr --lat-file lat.rdr --lon-file lon.rdr --geo2radar --fill 255
!generate_mask.py waterBody.rdr --max 0.5 -o waterMaskMintPy.rdr

'''