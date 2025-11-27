import numpy as np
import xarray as xr
import rioxarray  # registers .rio accessor
from pathlib import Path


pols=['hh', 'vv', 'hv']
for pol in pols:
    #nc_path = "/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/InSAR_results/S1/S1_InSAR_mintpy_geo.nc"
    #out_dir = "/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/InSAR_results/S1/geotiff"
    nc_path = f"/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/InSAR_results/P_{pol.upper()}/{pol.upper()}_Pband_InSAR_mintpy_geo.nc"
    out_dir = f"/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/InSAR_results/P_{pol.upper()}/geotiff"

    
    # helper: make a write-ready view (just renames lat/lon -> y/x)
    def as_xy(da):
        """
        Return a view of `da` with dims 'y','x' (needed by rioxarray).
        """
        assert "lat" in da.dims and "lon" in da.dims, "need lat/lon dims"
        return da.rename({"lat": "y", "lon": "x"})

    # open dataset with CF decoding
    ds = xr.open_dataset(nc_path, decode_coords="all")

    out_dir = Path(out_dir)
    (out_dir / "coherence").mkdir(parents=True, exist_ok=True)
    (out_dir / "timeseries").mkdir(parents=True, exist_ok=True)
    (out_dir / "masks").mkdir(parents=True, exist_ok=True)

    #(out_dir / "velocity").mkdir(parents=True, exist_ok=True)


    #coherence for each ifg pair
    if "coherence" in ds:
        coh = ds["coherence"]            # (ifg_pair, lat, lon)
        ifg_labels = ds["ifg_pair"].values

        for i in range(coh.sizes["ifg_pair"]):
            lab = str(ifg_labels[i])
            da_i = coh.isel(ifg_pair=i)
            da_xy = as_xy(da_i)          # (y, x)
            out_file = out_dir / "coherence" / f"coherence_{lab}.tif"
            print(f"Writing {out_file}")
            da_xy.rio.to_raster(out_file)

    #displacement timeseries
    if "timeseries" in ds:
        ts = ds["timeseries"]            # (time, lat, lon)
        times = ts["time"].values

        for i in range(ts.sizes["time"]):
            t = times[i]
            if np.issubdtype(times.dtype, np.datetime64):
                t_str = np.datetime_as_string(t, unit="D").replace("-", "")
            else:
                t_str = str(t)

            da_i = ts.isel(time=i)
            da_xy = as_xy(da_i)
            out_file = out_dir / "timeseries" / f"ts_{t_str}.tif"
            print(f"Writing {out_file}")
            da_xy.rio.to_raster(out_file)

    #masks
    for var_name, nice_name in [
        ("incAngle", "incAngle"),
        ("water_mask", "water_mask"),
        ("maskTempCoh", "maskTempCoh"),
    ]:
        if var_name in ds:
            da = ds[var_name]            # (lat, lon)
            da_xy = as_xy(da)
            out_file = out_dir / "masks" / f"{nice_name}.tif"
            print(f"Writing {out_file}")
            da_xy.rio.to_raster(out_file)

    ########
    # velocity, only for S1, comment out for P-band
    vel_candidates = ["velocity", "velocityStd", "intercept", "interceptStd", "residue"]

    for name in vel_candidates:
        if name in ds:
            da = ds[name]                # (lat, lon)
            da_xy = as_xy(da)
            out_file = out_dir / "velocity" / f"{name}.tif"
            print(f"Writing {out_file}")
            da_xy.rio.to_raster(out_file)
