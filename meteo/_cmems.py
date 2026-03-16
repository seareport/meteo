import logging
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd
import xarray as xr

from ._constants import CMEMS_TO_HYCOM_MAPPING
from ._constants import HYCOM_ARGS
from ._constants import HYCOM_COORD_ATTRS
from ._constants import HYCOM_GLOBAL_ATTRS
from ._constants import HYCOM_VAR_ATTRS
from ._constants import HYCOM_VARS
from ._literals import L_6Hours
from ._literals import L_CMEMS_Dataset
from ._literals import L_Days
from ._literals import L_Months

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)


def retrieve_cmems_phy_forecast_analysis(date: pd.Timestamp):
    import copernicusmarine as cm
    import xarray as xr

    def align_coords(ds, ds_ref):
        return ds.assign_coords(
            longitude=("longitude", ds_ref.longitude.values),
            latitude=("latitude", ds_ref.latitude.values)
        )

    if date.hour != 0:
        suffix = "PT6H-i"
    else:
        suffix = "P1D-m"

    # sea level
    dataset = "cmems_mod_glo_phy_anfc_merged-sl_PT1H-i"
    ds_wl = cm.open_dataset(
        dataset_id=dataset,
        variables=["total_sea_level"]
    ).sel(time=date).isel(depth=0)

    ds_3d = []
    for var in ["cur", "wcur", "so", "thetao"]:
        dataset = f"cmems_mod_glo_phy-{var}_anfc_0.083deg_{suffix}"
        ds = cm.open_dataset(
            dataset_id=dataset,
        ).sel(time=date)
        ds_3d.append(align_coords(ds, ds_wl))

    ds = xr.merge([*ds_3d, ds_wl])
    return ds


def retrieve_cmems_reanalysis(date):
    import copernicusmarine as cm

    dataset = f"cmems_mod_glo_phy_my_0.083deg_P1D-m"
    ds = cm.open_dataset(
        dataset_id=dataset,
    ).sel(time=date, method="nearest")
    return ds


def is_time_in_reanalysis(date):
    import copernicusmarine as cm
    dataset = f"cmems_mod_glo_phy_my_0.083deg_P1D-m"
    ds = cm.open_dataset(
        dataset_id=dataset,
    )
    times = ds.time.data
    if date > times[-1]:
        return False
    else:
        return True


def convert_cmems_to_hycom(ds: xr.Dataset) -> xr.Dataset:
    if "zos" in ds.data_vars:
        ds = ds.rename_vars({"zos": "total_sea_level"})
    rename_vars = {**CMEMS_TO_HYCOM_MAPPING, "total_sea_level": "surf_el"}
    ds = ds.rename(rename_vars)
    ds = ds[HYCOM_VARS]

    if "time" not in ds.dims:
        ds = ds.expand_dims("time")

    # u/v=0 where temperature has valid data (wet points) ! important otherwise hotstart fails
    wet_mask = ds["temperature"].notnull()
    for var in ["water_u", "water_v"]:
        ds[var] = ds[var].fillna(0.0).where(wet_mask)

    # assign HYCOM attributes
    for var in HYCOM_VARS:
        ds[var].attrs = HYCOM_VAR_ATTRS[var]
    for coord, attrs in HYCOM_COORD_ATTRS.items():
        if coord in ds.coords:
            ds[coord].attrs = attrs
    ds.attrs = HYCOM_GLOBAL_ATTRS

    return ds


def fix_north_boundary(filepath):
    with nc.Dataset(filepath, "r+") as ds:
        temp = ds.variables["temperature"]
        salt = ds.variables["salinity"]
        fill_t = np.nanmedian(temp[:, :, -2, :])
        fill_s = np.nanmedian(salt[:, :, -2, :])
        temp[0, 0, -1, 0] = fill_t
        salt[0, 0, -1, 0] = fill_s


def download_cmems(
    year: int,
    month: L_Months,
    day: L_Days,
    hour: L_6Hours,
    dataset: L_CMEMS_Dataset,
    output_dir: Path,
    output_format:str
):
    """
    Parameters
    ----------
    year : int
        Year to download (must be >= 1900).
    month : int
        Month to download (1-12).
    day : int
        Day to download (1-31).
    hour : int
        Hour to download (0/6/12 or 18)
    dataset : str
        Dataset from the Copernicus Marine Data Store. Ocean Physics (or 'cmems_mod_glo_phy') is the only one implemented for now.
    output_dir : Path
        Output directory for downloaded files.
    output_format : str
        export format for the netcdf file. Two options available: `cmems` (native/default) or `hycom`
    """
    import copernicusmarine as cm

    if dataset != "cmems_mod_glo_phy":
        raise NotImplementedError("only 'cmems_mod_glo_phy' (Ocean Physics) products are available for now")

    try:
        cm.login(check_credentials_valid=True)
    except:
        raise ValueError("Please setup your credentials with `copernicusmarine login`. More info at: https://toolbox-docs.marine.copernicus.eu/en/stable/usage/login-usage.html")

    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date = pd.Timestamp(year, month, day, hour)

    if is_time_in_reanalysis(date):
        logger.info("Reanalysis product data will be retrieved")
        ds = retrieve_cmems_reanalysis(date)
    else:
        logger.info("Analysis and Forecast product data will be retrieved")
        ds = retrieve_cmems_phy_forecast_analysis(date)

    if output_format == "cmems":
        ds.to_netcdf(f"{output_dir}/{dataset}_{date.strftime('%Y%m%d_%H')}.nc")
    elif output_format == "hycom":
        ds = convert_cmems_to_hycom(ds)
        outpath = f"{output_dir}/{dataset}_{date.strftime('%Y%m%d_%H')}_hycom.nc"
        ds.to_netcdf(outpath, **HYCOM_ARGS)
        fix_north_boundary(outpath)
    else:
        raise ValueError(f"format {output_format} not recognised. `cmems`/`hycom` only accepted")
