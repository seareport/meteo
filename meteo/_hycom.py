import logging
from pathlib import Path
from time import time

import numpy as np
import pandas as pd
import xarray as xr

from ._constants import HYCOM_MAX_DEPTH_INDEX
from ._constants import POTENTIAL_TEMP_CORRECTION
from ._constants import SUB_SAMPLE
from ._literals import L_Days
from ._literals import L_Months
from ._utils import normalize_longitude

logger = logging.getLogger(__name__)


def ConvertTemp(salt, temp, dep):
    import gsw

    pr = np.ones(temp.shape)
    pre = pr * dep[:, None, None]
    Pr = np.zeros(temp.shape)
    ptemp = gsw.pt_from_t(salt, temp, pre, Pr) * POTENTIAL_TEMP_CORRECTION
    return ptemp


def get_database(date, Bbox=None):
    if date > pd.Timestamp(2024, 8, 10):
        year = date.year
        str_ = (date-pd.Timedelta(days=1)).strftime("%Y%m%d")
        # we pull the previous run after 12 hours (model start is always at midday), hence 'YYMMDD12_t0012' format
        database = f"datasets/ESPC-D-V02/data/archive/{year}/US058GCOM-OPSnce.espc-d-031-hycom_fcst_glby008_{str_}12_t0012"
    elif date >= pd.Timestamp(2018, 12, 4) and date <= pd.Timestamp(2024, 8, 10):
        database = "GLBy0.08/expt_93.0"
    elif date >= pd.Timestamp(2018, 1, 1) and date < pd.Timestamp(2018, 12, 4):
        database = "GLBv0.08/expt_93.0"
    elif date >= pd.Timestamp(2017, 10, 1) and date < pd.Timestamp(2018, 1, 1):
        database = "GLBv0.08/expt_92.9"
    elif date >= pd.Timestamp(2017, 6, 1) and date < pd.Timestamp(2017, 10, 1):
        database = "GLBv0.08/expt_57.7"
    elif date >= pd.Timestamp(2017, 2, 1) and date < pd.Timestamp(2017, 6, 1):
        database = "GLBv0.08/expt_92.8"
    elif date >= pd.Timestamp(2016, 5, 1) and date < pd.Timestamp(2017, 2, 1):
        database = "GLBv0.08/expt_57.2"
    elif date >= pd.Timestamp(2016, 1, 1) and date < pd.Timestamp(2016, 5, 1):
        database = "GLBv0.08/expt_56.3"
    elif date >= pd.Timestamp(1994, 1, 1) and date < pd.Timestamp(2016, 1, 1):
        database = f"GLBv0.08/expt_53.X/data/{date.year}"
    else:
        raise ValueError(f"No data fro {date}!")
    return database


def get_idxs(date, database):
    if date >= pd.Timestamp.now():
        raise Exception("select time before today")
    else:
        if date >= pd.Timestamp(2024,8,10):
            baseurl = f"https://tds.hycom.org/thredds/dodsC/{database}_s3z.nc?lat[0:1:-1],lon[0:1:-1],time[0:1:-1],depth[0:1:-1]"
        else:
            baseurl = f"https://tds.hycom.org/thredds/dodsC/{database}?lat[0:1:-1],lon[0:1:-1],time[0:1:-1],depth[0:1:-1]"

    ds = xr.open_dataset(baseurl)
    lon = ds.lon.data
    lat = ds.lat.data
    times = ds.time.data
    ds.close()

    time_idx = np.where(date == times)[0]
    if len(time_idx) == 0:
        raise ValueError(f"No data for this date: {date}")

    return time_idx[0], 0, len(lon)-1, 0, len(lat)-1

def download_hycom(
    year: int,
    month: L_Months,
    day: L_Days,
    output_dir: Path,
    normalize: bool
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
    output_dir : Path,
        Output directory for downloaded files.
    normalize: bool
        Convert HYCOM longitude coordinates to the 0-360° convention.
    """
    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date = pd.Timestamp(year, month, day)

    database = get_database(date)
    logger.info(f"Fetching data for {date} from database {database}")

    time_idx, lon_idx1, lon_idx2, lat_idx1, lat_idx2 = get_idxs(date, database)
    selection_str = f"[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}][{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}]"

    if date < pd.Timestamp(2024,8,10):
        url_ssh = (
            f"https://tds.hycom.org/thredds/dodsC/{database}?lat[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}],"
            + f"lon[{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}],depth[0:1:-1],time[{time_idx}],"
            + f"surf_el[{time_idx}]{selection_str},"
            + f"water_u[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
            + f"water_v[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
            + f"water_temp[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
            + f"salinity[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str}"
        )
        ds = xr.open_dataset(url_ssh)
    else: # latest dataset has unaggregated (separated) variables
        ds_3d = []
        suffixes = ["s3z", "t3z", "u3z", "v3z"]
        variables = ["salinity", "water_temp", "water_u", "water_v"]
        for suffix, var in zip(suffixes, variables):
            ds_3d.append(xr.open_dataset(
                f"https://tds.hycom.org/thredds/dodsC/{database}_{suffix}.nc?lat[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}],"
                + f"lon[{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}],depth[0:1:-1],time[{time_idx}],"
                + f"{var}[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str}"))
        ds_ssh = xr.open_dataset(
            f"https://tds.hycom.org/thredds/dodsC/{database}_ssh.nc?lat[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}],"
            + f"lon[{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}],time[{time_idx}],"
            + f"surf_el[{time_idx}]{selection_str}")

        ds = xr.merge([*ds_3d, ds_ssh])

    if normalize:
        ds = normalize_longitude(ds, "lon") # defaults to 0-360° convention

    # convert in-situ temperature to potential temperature
    temp = ds.water_temp.values
    salt = ds.salinity.values
    dep = ds.depth.values

    ptemp = ConvertTemp(salt, temp, dep)
    # drop water_temp variable and add new temperature variable
    ds = ds.drop("water_temp")
    ds["temperature"] = (["time", "depth", "lat", "lon"], ptemp)
    ds.temperature.attrs = {
        "long_name": "Sea water potential temperature",
        "standard_name": "sea_water_potential_temperature",
        "units": "degC",
    }

    ds = ds.rename_dims({"lon": "xlon"})
    ds = ds.rename_dims({"lat": "ylat"})
    ds = ds.rename_vars({"lat": "ylat"})
    ds = ds.rename_vars({"lon": "xlon"})

    t0 = time()

    logger.info("Start writing nc file ...")
    foutname = f'{output_dir}/hycom_{date.strftime("%Y%m%d")}.nc'

    ds.to_netcdf(foutname, "w", unlimited_dims="time")
    ds.close()
    logger.info(f"It took {time()-t0} seconds to write nc file: {foutname}")
