import numpy as np
import rasterio
import matplotlib.pyplot as plt
from rasterio.mask import mask
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, Resampling
from rasterio.transform import array_bounds
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform
from pyproj import Transformer
import matplotlib.gridspec as gridspec
import fiona


def tiff_read_polygon(path_tif, geojson_polygon):
    '''
    Opens a dataset and returns its cropped subset based on the GeoJSON polygon. 

    Keyword arguments:
    path_tiff : path to the GeoTiff raster
    geojson_polygon : GeoJSON polygon (e.g. from geojson.io)

    Returns 
    '''

    polygon = shape(geojson_polygon) #shapely geometry object

    #make sure the GeoTIFF is in the same CRS as the polygon (epsg4326 == wgs84) 
    with rasterio.open(path_tif) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        project = lambda x, y: transformer.transform(x, y)
        projected_polygon = shapely_transform(project, polygon)
        #mask using the polygon
        out_image, out_transform = mask(src, [projected_polygon], crop=True)

        _, height, width = out_image.shape
        out_meta = src.meta.copy()
        out_meta.update({'width':width, 'height':height, 'transform':out_transform})
    
    #create a memory file to store the rasterio DatasetReader object
    #alternatively return out_image and out_meta as a ndarray and a dict
    #if this starts fucking with memory, look into Python's 'contextmanager'
    memfile = rasterio.MemoryFile()
    with memfile.open(**out_meta) as tmp_ds:
        tmp_ds.write(out_image)

    dataset = memfile.open() #this defaults to mode='r'
    return dataset


def numpy_to_rasterio(arr, meta):
    if len(arr.shape) == 2:
        arr = arr[np.newaxis, ...]
    memfile = rasterio.MemoryFile()
    with memfile.open(**meta) as tmp_ds:
        tmp_ds.write(arr)

    dataset = memfile.open() #this defaults to mode='r'
    return dataset


def reproject_to_crs(dataset: rasterio.io.DatasetReader, dst_crs='EPSG:4326', resampling=Resampling.nearest):
    '''
    Reprojects a rasterio dataset to a different CRS.

    Parameters:
        dataset : rasterio.io.DatasetReader
        dst_crs : CRS (default EPSG:4326)

    Returns:
        reprojected_dataset : rasterio.io.DatasetReader (reprojected data and updated metadata)
            
        
    '''
    dst_crs = rasterio.CRS.from_user_input(dst_crs)
    if dataset.crs == dst_crs:
        raise Exception('Target CRS is already the current CRS of the dataset.')
    
    dst_crs = dst_crs
    src_transform = dataset.transform
    src_crs = dataset.crs
    height, width = dataset.height, dataset.width
    bounds = array_bounds(height, width, src_transform)

    # Calculate new transform and size in EPSG:4326
    transform, width, height = calculate_default_transform(
        src_crs, dst_crs, width, height, *bounds
    )

    dtype = dataset.dtypes[0]
    bands = dataset.count

    '''
    if np.issubdtype(np.dtype(dtype), np.floating):
        dst_nodata = np.nan
    #elif np.iscomplexobj(dataset.read(1)):
    #    dst_nodata = np.nan + np.nan*1j
    #    print(dtype)
    else:
        dst_nodata = 0
    '''
    '''
    if np.issubdtype(np.dtype(dtype), np.integer):
        dst_nodata = 0
    else:
        dst_nodata = np.nan
    '''
    if np.issubdtype(np.dtype(dtype), np.integer):
        dst_nodata = 0
    else:
        dst_nodata = np.nan
    data = np.full((bands, height, width), fill_value=dst_nodata, dtype=dtype)
    #print(data.dtype)
    for i in range(bands):
        rasterio.warp.reproject(
            source=dataset.read(i + 1),
            destination=data[i],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=resampling,
            dst_nodata=dst_nodata
        )
        
    out_meta = dataset.meta.copy()
    out_meta.update({
        "crs": dst_crs,
        "transform": transform,
        "width": width,
        "height": height,
        "nodata" : dst_nodata ##### added nodata (tuesday 13 may, 11:37)
    })


    memfile = rasterio.MemoryFile()
    with memfile.open(**out_meta) as tmp_ds:
        tmp_ds.write(data)

    reprojected_dataset = memfile.open() #this defaults to mode='r'
    return reprojected_dataset 

def match_grid(src_ds: rasterio.io.DatasetReader, target_meta:dict, resampling=None):
    '''
    Regrids raster image to match the transform, shape, and CRS of another dataset.

    Parameters:
        src_ds : rasterio.io.DatasetReader (SAR image in EPSG:4326)
        target_meta : dict (metadata of the target grid)
        resampling : rasterio.enums.Resampling

    Returns:
        regridded : np.ndarray (resampled image on a new grid)
    '''
    if src_ds.crs != target_meta['crs']:
        raise Exception('The coordinate of the two datasets do not match')
    

    #compute source and target pixel sizes
    src_px_x, src_px_y = abs(src_ds.transform.a), abs(src_ds.transform.e)
    tgt_px_x, tgt_px_y = abs(target_meta['transform'].a), abs(target_meta['transform'].e)

    #determine resampling automatically if not provided
    if resampling is None:
        if tgt_px_x >= src_px_x or tgt_px_y >= src_px_y:
            resampling = Resampling.average  #downsampling (at least one dimension)
        else:
            resampling = Resampling.nearest  # upsampling
    
    bands = src_ds.count
    dtype = src_ds.dtypes[0]

    if np.issubdtype(np.dtype(dtype), np.integer):
        dst_nodata = 0

    else:
        dst_nodata = np.nan

    regridded = np.full((bands, target_meta['height'], target_meta['width']), fill_value=dst_nodata, dtype=dtype)

    for i in range(bands):
        rasterio.warp.reproject(
            source=src_ds.read(i + 1),
            destination=regridded[i],
            src_transform=src_ds.transform,
            src_crs=src_ds.crs,
            dst_transform=target_meta['transform'],
            dst_crs=target_meta['crs'],
            dst_nodata = dst_nodata,
            resampling=resampling
        )

    out_meta = target_meta.copy()
    out_meta.update({
        "count": bands,
        "dtype": dtype,
        "nodata": dst_nodata
    })
    
    memfile = rasterio.MemoryFile()
    with memfile.open(**out_meta) as tmp_ds:
        tmp_ds.write(regridded)

    regridded_dataset = memfile.open() #this defaults to mode='r'
    return regridded_dataset 

def dataset_intersection_mask(datasets):
    """
    Takes the intersection of multiple overlapping datasets, masking out any pixel where at least one dataset has nodata.

    Parameters:
        datasets : list of rasterio.io.DatasetReader

    Returns:
        joint_mask : binary mask used to mask invalid pixels. Apply using np.where(joint_mask, arr, ds.nodata)
    """
    if len(datasets) < 2:
        raise ValueError("Provide at least two datasets.")

    shape = datasets[0].shape
    for ds in datasets:
        if ds.shape != shape:
            raise Exception("All datasets must have the same shape.")

    # Read all data into list
    data_arrays = [ds.read() for ds in datasets]

    # Construct a valid mask
    masks = []
    for arr, ds in zip(data_arrays, datasets):
        m = (arr != ds.nodata) & ~np.isnan(arr)
        masks.append(m)
    joint_mask = np.logical_and.reduce(masks)

    return joint_mask

def mask_scene_edges_rowwise(src_ds: rasterio.io.DatasetReader, n=5, transpose=False) -> rasterio.io.DatasetReader:
    """
    Masks n pixels on both sides of valid data in each row of a rasterio dataset.
    Used to eliminate edge artifacts in UAVSAR images.
    Recommended to apply twice (cutting both from columns and rows), first with transpose=False, then with transpose=True
    Parameters:
        src_ds : rasterio.io.DatasetReader -- input dataset with NaNs marking invalid pixels
        n      : int -- number of pixels to mask inward from each valid edge

    Returns:
        rasterio.io.DatasetReader -- memory-resident dataset with masked edges
    """

    data = src_ds.read(1).copy()
    COMPLEX = False
    if np.iscomplexobj(data):
        COMPLEX = True
        datatype = 'complex64'
    else:
        datatype = 'float32'
    if transpose:
        data = data.T
    valid = ~np.isnan(data)

    for ix in range(data.shape[0]):
        r = valid[ix, :]
        valid_pixels = np.argwhere(r)
        if valid_pixels.size == 0:
            continue  # skip row if no valid data
        first_valid = valid_pixels.min()
        last_valid = valid_pixels.max()

        data[ix, first_valid:first_valid + n] = np.nan
        data[ix, last_valid - n + 1:last_valid + 1] = np.nan

    out_meta = src_ds.meta.copy()
    
    out_meta.update({
        'dtype': datatype,
        'nodata': np.nan
    })

    memfile = rasterio.MemoryFile()
    with memfile.open(**out_meta) as dst:
        if transpose:
            data = data.T
        dst.write(data.astype(datatype), 1)
        dst.update_tags(**src_ds.tags())

    return memfile.open()

def crop_ds(ds, aoi_shapefile):
    '''
    Crop a Rasterio dataset using a shapefile (from QGIS or similar).
    Parameters:
        ds: rasterio.io.DatasetReader - source dataset
        aoi_shapefile: path to a .shp file containing the AOI
    
    Returns:
        rasterio.io.DatasetReader - memory-resident dataset cropped to the desired AOI
    '''
    with fiona.open(aoi_shapefile, "r") as shapefile:
        geoms = [feature["geometry"] for feature in shapefile]

    out_image, out_transform = mask(ds, geoms, crop=True)
    out_meta = ds.meta.copy()

    # Update meta with new dimensions and transform
    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform
    })

    src_tags = ds.tags()

    memfile = rasterio.MemoryFile()
    with memfile.open(**out_meta) as tmp_ds:
        tmp_ds.update_tags(**src_tags)
        tmp_ds.write(out_image)

    return memfile.open()

def write_ds(data, ds_meta, path_out):
    with rasterio.open(path_out, 'w', **ds_meta) as f:
        f.write(data, 1)