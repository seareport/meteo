import calendar
import itertools
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import tqdm.auto
import xarray as xr

from ._constants import ATTRIBUTES
from ._constants import ERA5_REQUIRED_VARS
from ._constants import ERA5_SFLUX_MAPPING
from ._utils import auto_pad_lon
from ._utils import write_file

logger = logging.getLogger(__name__)

def create_year_month_subfolder(outdir: Path, year: int, month: int):
    sflux_monthly_outdir = outdir / f"{year}.{month:02d}"
    sflux_monthly_outdir.mkdir(parents=True, exist_ok=True)
    return sflux_monthly_outdir


def get_base_sflux_ds(grib_ds: xr.Dataset):
    time = grib_ds.time.values[0]
    year, month, day = pd.to_datetime(time).year, pd.to_datetime(time).month, pd.to_datetime(time).day
    lon = grib_ds.longitude.values
    lat = grib_ds.latitude.values[::-1] # flip to south->north as in pyschism
    nx_grid, ny_grid = np.meshgrid(lon, lat)

    ds = xr.Dataset(
        coords={
            "time": ("time", grib_ds.time.values, {**ATTRIBUTES["time"], "base_date": [year, month, day, 0]}),
        },
        data_vars={
            "lon": (("ny_grid", "nx_grid"), nx_grid, ATTRIBUTES["lon"]),
            "lat": (("ny_grid", "nx_grid"), ny_grid, ATTRIBUTES["lat"]),
        },
        attrs={"Conventions": "CF-1.0"},
    )
    return ds


def compute_spfh(ds: xr.Dataset) -> xr.DataArray:
    """
    Compute specific humidity (sh2) from 2m dewpoint temperature and mean sea level pressure.

    Uses Bolton (1980) vapor pressure formula and standard specific humidity derivation:
        e1   = 6.112 * exp((17.67 * Td) / (Td + 243.5))    [hPa] - Bolton, Monthly Weather Review 108, 1046-1053
        spfh = (0.622 * e) / (P_hPa - 0.378 * e)           [kg/kg] - from ideal gas law; ε = Mw/Md = 18.015/28.964 ≈ 0.622
    """
    var = list(ds.variables)
    if "d2m" not in var or "msl" not in var:
        logger.warning("Skipping: Both 'd2m' and 'msl' variables are required to compute specific humidity.")
        return ds
    d2m = ds['d2m'] # 2m dewpoint temperature in Kelvin
    msl = ds['msl'] # mean sea level pressure in Pa -> convert to hPa
    Td = d2m - 273.15
    e1 = 6.112*np.exp((17.67*Td)/(Td + 243.5))
    spfh = (0.622*e1)/(msl*0.01 - (0.378*e1))
    ds["sh2"] = spfh
    return ds


def stack_step_time(ds: xr.Dataset) -> xr.Dataset:
    ds_out = ds.stack(valid=("time", "step"))
    ds_out = ds_out.swap_dims({"valid": "valid_time"})
    ds_out = ds_out.dropna(dim="valid_time", how="all")
    ds_out = ds_out.drop_vars(["time", "step", "valid"]).rename({"valid_time": "time"})
    return ds_out.transpose("time", "latitude", "longitude")


def get_sflux_ds(grib_ds: xr.Dataset, grib_var: str, sflux_var: str) -> xr.Dataset:
    logger.info(f"convert {grib_var} to {sflux_var}")
    ds = get_base_sflux_ds(grib_ds)
    data = grib_ds[grib_var].values[:, ::-1, :]
    ds[sflux_var] = (("time", "ny_grid", "nx_grid"), data, ATTRIBUTES[sflux_var])
    return ds


def _get_era5(grib_ds: xr.Dataset, outdir: Path, group: str, overwrite: bool):
    var_map = ERA5_SFLUX_MAPPING[group]
    if group in ["prc", "rad"]:
        grib_ds = stack_step_time(grib_ds)
    if "sh2" in var_map:
        grib_ds = compute_spfh(grib_ds)

    datasets = [get_sflux_ds(grib_ds, g, s) for g, s in var_map.items()]
    merged = xr.merge(datasets, compat="override")

    return merged


def check_required_variables(ds: xr.Dataset, group: str):
    required = ERA5_REQUIRED_VARS.get(group, set())
    missing = required - set(ds.variables)
    if missing:
        raise ValueError(f"Missing required variables for '{group}': {missing}")


def era5_to_sflux(file: Path, group: str, output_dir: Path, overwrite: bool) -> None:
    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    grib_ds = xr.open_dataset(file)
    check_required_variables(grib_ds, group)

    # pad longitude by default -> consider removing this when implementing regional models
    grib_ds = auto_pad_lon(grib_ds, method_longitude="auto")

    # convert to sflux format (SCHISM inputs)
    schism_ds = _get_era5(grib_ds, output_dir, group, overwrite)
    filename = output_dir / f"sflux_{file.stem}_{group}.nc"
    write_file(schism_ds, filename, overwrite=overwrite)

    # add simple text file schism_input.txt in the output directory (see SCHISM manual)
    schism_input_file = output_dir / "sflux_inputs.txt"
    if overwrite or not schism_input_file.exists():
        schism_input_file.write_text("&sflux_inputs\n/\n")
