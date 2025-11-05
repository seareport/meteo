import logging
from pathlib import Path
from time import time
from typing import Annotated

import numpy as np
import pandas as pd
import xarray as xr
from cyclopts import Parameter

from ._constants import Bbox
from ._constants import HYCOM_MAX_DEPTH_INDEX
from ._constants import POTENTIAL_TEMP_CORRECTION
from ._constants import SUB_SAMPLE
from ._literals import L_Days
from ._literals import L_HYCOM_Dataset
from ._literals import L_Months

logger = logging.getLogger(__name__)


def ConvertTemp(salt, temp, dep):
    # nz = temp.shape[0]
    # ny = temp.shape[1]
    # nx = temp.shape[2]
    import seawater as sw

    pr = np.ones(temp.shape)
    pre = pr * dep[:, None, None]
    Pr = np.zeros(temp.shape)
    ptemp = sw.ptmp(salt, temp, pre, Pr) * POTENTIAL_TEMP_CORRECTION
    return ptemp


def get_database(date, Bbox=None):
    if date >= pd.Timestamp(2018, 12, 4):
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


def get_idxs(date, database, bbox):
    if date >= pd.Timestamp.now():
        raise Exception("select time before today")
    else:
        baseurl = f"https://tds.hycom.org/thredds/dodsC/{database}?lat[0:1:-1],lon[0:1:-1],time[0:1:-1],depth[0:1:-1]"

    ds = xr.open_dataset(baseurl)
    lon = ds.lon.data
    lat = ds.lat.data
    times = ds.time.data
    ds.close()

    time_idx = np.where(date == times)[0]
    if len(time_idx) == 0:
        raise Exception(f"No data for this date: {date}")

    lat_idxs = np.where((lat >= bbox.ymin - 0.5) & (lat <= bbox.ymax + 0.5))[0]
    lon_idxs = np.where((lon >= bbox.xmin - 0.5) & (lon <= bbox.xmax + 0.5))[0]

    return time_idx[0], lon_idxs[0], lon_idxs[-1], lat_idxs[0], lat_idxs[-1]


def download_hycom(
    year: int,
    month: L_Months,
    day: Annotated[L_Days, Parameter(show_choices=False)],
    dataset: L_HYCOM_Dataset = "Operational",
    output_dir: Path | None = None,
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
    output_dir : Path, default: system-specific
        Output directory for downloaded files. Data is saved to a 'HYCOM'
        subdirectory within this path. Defaults to a platform-specific location.
    dataset: str
        If the dataset type is "Operational" or "Reanalysis"
    """

    if dataset == "Reanalysis":
        raise NotImplementedError("Reanalysis not implemented yet")

    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bbox = Bbox()
    date = pd.Timestamp(year, month, day)

    database = get_database(date)
    logger.info(f"Fetching data for {date} from database {database}")

    time_idx, lon_idx1, lon_idx2, lat_idx1, lat_idx2 = get_idxs(date, database, bbox)
    selection_str = f"[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}][{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}]"

    url_ssh = (
        f"https://tds.hycom.org/thredds/dodsC/{database}?lat[{lat_idx1}:{SUB_SAMPLE}:{lat_idx2}],"
        + f"lon[{lon_idx1}:{SUB_SAMPLE}:{lon_idx2}],depth[0:1:-1],time[{time_idx}],"
        + f"surf_el[{time_idx}]{selection_str},"
        + f"water_u[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
        + f"water_v[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
        + f"water_temp[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str},"
        + f"salinity[{time_idx}][0:1:{HYCOM_MAX_DEPTH_INDEX}]{selection_str}"
    )

    foutname = f'hycom_{date.strftime("%Y%m%d")}.nc'
    logger.info(f"filename is {foutname}")
    ds = xr.open_dataset(url_ssh)

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
    logger.info("Start writing nc file!")
    ds.to_netcdf(
        foutname,
        "w",
        unlimited_dims="time",
        encoding={
            "temperature": {
                "dtype": "h",
                "_FillValue": -30000.0,
                "scale_factor": 0.001,
                "add_offset": 20.0,
                "missing_value": -30000.0,
            }
        },
    )
    ds.close()
    logger.info(f"It took {time()-t0} seconds to write nc file!")
