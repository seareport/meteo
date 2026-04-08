import logging
from pathlib import Path

import pandas as pd

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


def download_cmems(
    year: int,
    month: L_Months,
    day: L_Days,
    hour: L_6Hours,
    dataset: L_CMEMS_Dataset,
    output_dir: Path,
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
    hour :
        Hour to download (0/6/12 or 18)
    dataset : str
        Dataset from the Copernicus Marine Data Store. Ocean Physics (or 'cmems_mod_glo_phy') is the only one implemented for now.
    output_dir : Path
        Output directory for downloaded files.
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

    ds.to_netcdf(f"{output_dir}/cmems_mod_glo_phy_{date.strftime('%Y%m%d_%H')}.nc")
