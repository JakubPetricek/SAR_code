import os
import numpy as np
import xarray as xr

pols = ['vv', 'hh', 'hv']
for pol in pols:
    #sentinel 1, uncomment ds_velocity
    #in_path = os.path.abspath("/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/orbit_131/stack_3conn_iono/mintpy")

    in_path = os.path.abspath(f'/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/S1_SLC/Pband_InSAR/dhorse_stack/mosaic_{pol}/mintpy')
    out_path = os.path.abspath(
        f"/Data/jpe128/ResearchData/IFT/EarthObservation/Common/jakub/deadhorse/InSAR_results/P_{pol.upper()}"
    )
    os.chdir(in_path)

    ds_coh        = xr.open_dataset("geo/geo_coherence.h5",    engine="h5netcdf", phony_dims="access")
    ds_maskTemp   = xr.open_dataset("geo/geo_maskTempCoh.h5",  engine="h5netcdf", phony_dims="access")
    ds_waterMask  = xr.open_dataset("geo/geo_waterMask.h5",    engine="h5netcdf", phony_dims="access")
    ds_timeseries = xr.open_dataset("geo/geo_timeseries.h5",   engine="h5netcdf", phony_dims="access")
    ds_incAngle   = xr.open_dataset("geo/geo_incidenceAngle.h5",engine="h5netcdf", phony_dims="access")

    ds_velocity = None
    #ds_velocity   = xr.open_dataset("geo/geo_velocity.h5",     engine="h5netcdf", phony_dims="access")  # S1 only

    #build lat / lon from geo_coherence attrs
    lat_first = float(ds_coh.attrs["Y_FIRST"])
    lon_first = float(ds_coh.attrs["X_FIRST"])
    lat_step  = float(ds_coh.attrs["Y_STEP"])
    lon_step  = float(ds_coh.attrs["X_STEP"])

    n_ifg, n_y, n_x = ds_coh["coherence"].shape

    latitudes  = lat_first + np.arange(n_y) * lat_step
    longitudes = lon_first + np.arange(n_x) * lon_step

    #COHERENCE: dims (ifg_pair, lat, lon) + date_start/end/mid
    coh = ds_coh["coherence"]

    t_dim, y_dim, x_dim = coh.dims  # phony_dim_0, phony_dim_1, phony_dim_2
    coh = coh.rename({t_dim: "ifg_pair", y_dim: "lat", x_dim: "lon"})

    #attach lat/lon
    coh = coh.assign_coords(
        lat=("lat", latitudes),
        lon=("lon", longitudes),
    )

    #build date coords from 'date' variable (YYYYMMDD)
    date_arr = ds_coh["date"].values.astype("U8")  # shape (n_ifg, 2)
    d1_str = date_arr[:, 0]
    d2_str = date_arr[:, 1]

    #YYYYMMDD -> YYYY-MM-DD -> datetime64[D]
    d1_iso = np.array([f"{s[0:4]}-{s[4:6]}-{s[6:8]}" for s in d1_str])
    d2_iso = np.array([f"{s[0:4]}-{s[4:6]}-{s[6:8]}" for s in d2_str])

    d1 = d1_iso.astype("datetime64[D]")
    d2 = d2_iso.astype("datetime64[D]")
    d_mid = d1 + (d2 - d1) // 2

    ifg_label = np.array([f"{a}_{b}" for a, b in zip(d1_str, d2_str)])

    coh = coh.assign_coords(
        ifg_pair=("ifg_pair", ifg_label),
        date_start=("ifg_pair", d1),
        date_end=("ifg_pair", d2),
        date_mid=("ifg_pair", d_mid),
    )

    #apply MintPy's dropIfgram mask if present
    if "dropIfgram" in ds_coh:
        valid_ifg = ds_coh["dropIfgram"].values  #boolean
        coh = coh.isel(ifg_pair=valid_ifg)

    coh.name = "coherence"  # nice variable name
    coh.attrs.update(ds_coh["coherence"].attrs)


    #TIMESERIES: dims (time, lat, lon), plus bperp(time)
    ts = ds_timeseries["timeseries"]
    t2_dim, y2_dim, x2_dim = ts.dims

    ts = ts.rename({t2_dim: "time", y2_dim: "lat", x2_dim: "lon"})
    ts = ts.assign_coords(
        lat=("lat", latitudes),
        lon=("lon", longitudes),
    )

    # date for timeseries: ds_timeseries["date"] is 1-D YYYYMMDD
    ts_date_str = ds_timeseries["date"].values.astype("U8")
    ts_date_iso = np.array([f"{s[0:4]}-{s[4:6]}-{s[6:8]}" for s in ts_date_str])
    ts_time = ts_date_iso.astype("datetime64[D]")

    ts = ts.assign_coords(time=("time", ts_time))
    ts.name = "timeseries"
    ts.attrs.update(ds_timeseries["timeseries"].attrs)

    # bperp: same time dimension
    bperp = ds_timeseries["bperp"]
    b_dim = bperp.dims[0]
    bperp = bperp.rename({b_dim: "time"})
    bperp = bperp.assign_coords(time=("time", ts_time))
    bperp.name = "bperp"
    bperp.attrs.update(ds_timeseries["bperp"].attrs)

    #MASKS: IA, waterMask, maskTempCoh; dims (lat, lon)
    def convert_mask(ds_mask, var_name, new_name):
        da = ds_mask[var_name]
        y_dim, x_dim = da.dims
        da = da.rename({y_dim: "lat", x_dim: "lon"})
        da = da.assign_coords(lat=("lat", latitudes),
                            lon=("lon", longitudes))
        da.name = new_name
        da.attrs.update(ds_mask[var_name].attrs)
        return da
    incAngle = convert_mask(ds_incAngle, "incidenceAngle", "incAngle")
    water_mask = convert_mask(ds_waterMask, "mask", "water_mask")
    temp_coh_mask = convert_mask(ds_maskTemp, "mask", "maskTempCoh")

    if ds_velocity is not None:
        # S1 only: VELOCITY PRODUCTS: all 2-D vars to (lat, lon)
        vel_vars = {}
        for vname, da in ds_velocity.data_vars.items():
            y_dim, x_dim = da.dims
            da2 = da.rename({y_dim: "lat", x_dim: "lon"})
            da2 = da2.assign_coords(lat=("lat", latitudes),
                                    lon=("lon", longitudes))
            da2.attrs.update(da.attrs)
            vel_vars[vname] = da2  # e.g. velocity, velocityStd, intercept, ...

    if ds_velocity is not None:
        #build a single merged Dataset (optional, but convenient)
        ds_out = xr.Dataset(
            data_vars={
                "coherence": coh,
                "timeseries": ts,
                "bperp": bperp,
                "incAngle" : incAngle,
                "water_mask": water_mask,
                "maskTempCoh": temp_coh_mask,
                **vel_vars,     # velocity, velocityStd, intercept, ...
            },
            coords={
                "lat": ("lat", latitudes),
                "lon": ("lon", longitudes),
                "ifg_pair": coh["ifg_pair"],
                "time": ts["time"],
                "date_start": ("ifg_pair", coh["date_start"].values),
                "date_end": ("ifg_pair", coh["date_end"].values),
                "date_mid": ("ifg_pair", coh["date_mid"].values),
            },
        )

    else:
        ds_out = xr.Dataset(
            data_vars={
                "coherence": coh,
                "timeseries": ts,
                "bperp": bperp,
                "incAngle" : incAngle,
                "water_mask": water_mask,
                "maskTempCoh": temp_coh_mask,
            },
            coords={
                "lat": ("lat", latitudes),
                "lon": ("lon", longitudes),
                "ifg_pair": coh["ifg_pair"],
                "time": ts["time"],
                "date_start": ("ifg_pair", coh["date_start"].values),
                "date_end": ("ifg_pair", coh["date_end"].values),
                "date_mid": ("ifg_pair", coh["date_mid"].values),
            },
        )

    #merge global attrs from individual files (prefix to avoid collisions)
    ds_out.attrs.update({f"coh_{k}": v for k, v in ds_coh.attrs.items()})
    ds_out.attrs.update({f"ts_{k}": v for k, v in ds_timeseries.attrs.items()})
    ds_out.attrs.update({f"wm_{k}": v for k, v in ds_waterMask.attrs.items()})
    ds_out.attrs.update({f"mtc_{k}": v for k, v in ds_maskTemp.attrs.items()})
    ds_out.attrs.update({f"ia_{k}": v for k, v in ds_incAngle.attrs.items()})
    if ds_velocity is not None:
        ds_out.attrs.update({f"vel_{k}": v for k, v in ds_velocity.attrs.items()})

    #save to netcdf
    os.makedirs(out_path, exist_ok=True)
    ds_out.to_netcdf(os.path.join(out_path, f"{pol.upper()}_Pband_InSAR_mintpy_geo.nc"))