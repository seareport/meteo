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
from ._constants import F1280_SFLUX_MAPPING
from ._utils import auto_pad_lat
from ._utils import auto_pad_lon
from ._utils import get_grib_path
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
    Compute specific humidity (sh2) from 2m dewpoint temperature and surface pressure.

    Uses Bolton (1980) vapor pressure formula and standard specific humidity derivation:
        e1   = 6.112 * exp((17.67 * Td) / (Td + 243.5))    [hPa] - Bolton, Monthly Weather Review 108, 1046-1053
        spfh = (0.622 * e) / (P_hPa - 0.378 * e)           [kg/kg] - from ideal gas law; ε = Mw/Md = 18.015/28.964 ≈ 0.622
    """
    var = list(ds.variables)
    if "d2m" not in var or "sp" not in var:
        raise ValueError("Skipping: Both 'd2m' and 'sp' variables are required to compute specific humidity.")
    d2m = ds['d2m'] # 2m dewpoint temperature in Kelvin
    psr = ds['sp'] * 0.01 # surface pressure in Pa -> convert to hPa
    Td = d2m - 273.15
    e1 = 6.112*np.exp((17.67*Td)/(Td + 243.5))
    spfh = (0.622*e1)/(psr - (0.378*e1))
    ds["sh2"] = spfh
    return ds


def stack_step_time(ds: xr.Dataset) -> xr.Dataset:
    times = ds.time.values
    steps = ds.step.values
    # for averaged variables, the averaging processing has been done for the hour prior.
    # so it makes more sense to set the valid time to the middle of the hour, i.e. 30 minutes earlier than the end of the step
    # see https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview for ERA5
    # see https://confluence.ecmwf.int/spaces/CKB/pages/76414402/ERA5+data+documentation#ERA5:datadocumentation-Meanrates/fluxesandaccumulations for ECMWF
    valid_times = (times[:, None] + steps[None, :]).ravel() - pd.Timedelta(minutes=30)

    results = []
    for t in range(ds.sizes["time"]):
        for s in range(ds.sizes["step"]):
            sel = ds.isel(time=t, step=s).load()
            vt = valid_times[t * ds.sizes["step"] + s]
            sel = sel.expand_dims(time=[vt])
            results.append(sel)

    ds_out = xr.concat(results, dim="time", coords="all")
    ds_out = ds_out.dropna(dim="time", how="all")   # drop init/step combos with no GRIB message
    return ds_out.transpose("time", "latitude", "longitude")


def get_sflux_ds(
    grib_ds: xr.Dataset,
    grib_var: str,
    sflux_var: str,
) -> xr.Dataset:
    logger.info(f"convert {grib_var} to {sflux_var}")
    data = grib_ds[grib_var].values[:, ::-1, :]
    ds = get_base_sflux_ds(grib_ds)
    ds[sflux_var] = (("time", "ny_grid", "nx_grid"), data, ATTRIBUTES[sflux_var])

    return ds


def _get_era5(grib_ds: xr.Dataset, group: str):
    var_map = ERA5_SFLUX_MAPPING[group]
    if group in ["prc", "rad"]:
        grib_ds = stack_step_time(grib_ds)
    if "sh2" in var_map:
        grib_ds = grib_ds.rename({"msl": "sp"})
        grib_ds = compute_spfh(grib_ds)
        grib_ds = grib_ds.rename({"sp": "msl"})

    datasets = [get_sflux_ds(grib_ds, g, s) for g, s in var_map.items()]
    merged = xr.merge(datasets, compat="override")

    return merged


def _get_f1280(files: xr.Dataset, group: str):
    var_map = F1280_SFLUX_MAPPING[group]
    file_by_var = {f.stem.split(".")[-1]: f for f in files}
    is_accumulated = group in ["prc", "rad"]

    if group == "air" and "sh2" not in file_by_var:
        logger.info("'sh2' file not found, computing from '2d' and 'sp'")
        ds_2d = xr.open_dataset(file_by_var["2d"])
        ds_psr = xr.open_dataset(file_by_var["sp"])
        merged = xr.merge([ds_2d, ds_psr], compat="override")
        sh2_ds = compute_spfh(merged)[["sh2"]]
        del ds_2d, ds_psr, merged

    datasets_ = []
    for grib_var, schism_var in var_map.items():
        if grib_var == "sh2" and "sh2" not in file_by_var:
            grib_ds = sh2_ds
        else:
            grib_ds = xr.open_dataset(file_by_var[grib_var])
        if is_accumulated:
            grib_ds = grib_ds.diff(dim="step", label="lower")
        grib_ds = grib_ds.load() # materialize before reindexing (cfgrib vectorized indexing blows up the memory)
        grib_ds = stack_step_time(grib_ds)
        grib_ds = auto_pad_lon(grib_ds, method_longitude="auto")
        grib_ds = auto_pad_lat(grib_ds, method_latitude="median", side="north")
        ds = get_sflux_ds(
            grib_ds,
            grib_var,
            schism_var,
        )

        if grib_var in ("strd", "ssrd"):
            ds[schism_var] = ds[schism_var] / 3600
        datasets_.append(ds)
    merged = xr.merge(datasets_,compat="override")
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

    grib_ds = auto_pad_lon(grib_ds, method_longitude="auto")

    schism_ds = _get_era5(grib_ds, group)
    filename = output_dir / f"sflux_{file.stem}_{group}.nc"

    base_date = schism_ds.time.attrs["base_date"]
    encoding = {
        "time": {
            "units": f"days since {base_date[0]}-{base_date[1]:02d}-{base_date[2]:02d}",
            "dtype": "float32",
        }
    }

    write_file(schism_ds, filename, overwrite=overwrite, encoding=encoding)

    # add simple text file schism_input.txt in the output directory (see SCHISM manual)
    schism_input_file = output_dir / "sflux_inputs.txt"
    if overwrite or not schism_input_file.exists():
        schism_input_file.write_text("&sflux_inputs\n/\n")


def f1280_to_sflux(
    group: str,
    year: int,
    month: int,
    f1280_dir: Path,
    output_dir: Path,
    overwrite: bool,
) -> None:
    """
    Convert per-variable F1280 GRIB files to SCHISM sflux NetCDF.

    The files needed for the F1280 GRIB files are:
        * For 'air': [msl, u10, v10, t2m, sh2 (or 2d+msl)]
        * For 'rad': [ssrd, strd]
        * For 'prc': [tp]

    Parameters
    ----------
    group : str
        Variable group: 'air', 'rad', or 'prc'.
    year : int
        Year of the data to process.
    month : int
        Month of the data to process.
    output_dir : Path
        Output directory for sflux NetCDF files.
    overwrite : bool
        Whether to overwrite existing output files.
    """
    variables = F1280_SFLUX_MAPPING[group].keys()

    files = []
    missing = []
    for var in variables:
        fpath = f1280_dir / get_grib_path(var, year, month, "F1280")
        if fpath.exists():
            files.append(fpath)
        else:
            missing.append(var)

    if "sh2" in missing:
        logger.info("'sh2' file not found, will attempt to compute from '2d' and 'sp'")
        missing.remove("sh2")
        for fallback_var in ["2d", "sp"]:
            fb_path = f1280_dir / get_grib_path(fallback_var, year, month, "F1280")
            if not fb_path.exists():
                raise FileNotFoundError(
                    f"Neither 'sh2' nor '{fallback_var}' found in {fb_path}. "
                    "Need either 'sh2' directly or both '2d' and 'msl' to compute it."
                )
            if fb_path not in files:
                files.append(fb_path)

    if missing:
        raise FileNotFoundError(f"Missing F1280 files for group '{group}': {missing}")

    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    schism_ds = _get_f1280(files, group)
    filename = output_dir / f"sflux_F1280.{year}.{month:02d}_{group}.nc"

    base_date = schism_ds.time.attrs["base_date"]
    encoding = {
        "time": {
            "units": f"days since {base_date[0]}-{base_date[1]:02d}-{base_date[2]:02d}",
            "dtype": "float32",
        }
    }

    write_file(schism_ds, filename, overwrite=overwrite, encoding=encoding)

    # add simple text file schism_input.txt in the output directory (see SCHISM manual)
    schism_input_file = output_dir / "sflux_inputs.txt"
    if overwrite or not schism_input_file.exists():
        schism_input_file.write_text("&sflux_inputs\n/\n")
