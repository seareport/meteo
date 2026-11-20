import calendar
import datetime
import itertools
import logging
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import tqdm.auto
import xarray as xr

from ._constants import ATTRIBUTES
from ._constants import ERA5_REQUIRED_VARS
from ._constants import ERA5_SFLUX_MAPPING
from ._constants import MARS_SFLUX_MAPPING
from ._utils import auto_pad_lat
from ._utils import auto_pad_lon
from ._utils import compute_duration_tag
from ._utils import default_out_grid
from ._utils import detect_name
from ._utils import ensure_structured_latlon
from ._utils import GRIB_SUFFIXES
from ._utils import grid_slug
from ._utils import infer_grid
from ._utils import open_meteo_file
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
    lat = grib_ds.latitude.values
    if lat[0] > lat[-1]:
        lat = lat[::-1] # flip to south->north as in pyschism
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
    Compute specific humidity (sh2) from 2m dewpoint temperature ('d2m', K) and surface pressure ('sp', Pa).

    Uses Bolton (1980) vapor pressure formula and standard specific humidity derivation:
        e1   = 6.112 * exp((17.67 * Td) / (Td + 243.5))    [hPa] - Td in °C; Bolton, Monthly Weather Review 108, 1046-1053
        spfh = (0.622 * e1) / (P_hPa - 0.378 * e1)         [kg/kg] - from ideal gas law; ε = Mw/Md = 18.015/28.964 ≈ 0.622
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


def stack_step_time(ds: xr.Dataset, start: datetime.datetime | None = None) -> xr.Dataset:
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
    if start is not None:
        # keep only valid times from 00:00 of the request day, since we shift -30 min: from 23:30 of the previous day
        ds_out = ds_out.sel(time=slice(pd.Timestamp(start) - pd.Timedelta(minutes=30), None))
    return ds_out.transpose("time", "latitude", "longitude")


def get_sflux_ds(
    grib_ds: xr.Dataset,
    grib_var: str,
    sflux_var: str,
) -> xr.Dataset:
    logger.info(f"convert {grib_var} to {sflux_var}")
    data = grib_ds[grib_var].values
    if grib_ds.latitude.values[0] > grib_ds.latitude.values[-1]:
        data = data[:, ::-1, :]
    ds = get_base_sflux_ds(grib_ds)
    ds[sflux_var] = (("time", "ny_grid", "nx_grid"), data, ATTRIBUTES[sflux_var])

    return ds


def _get_era5(grib_ds: xr.Dataset, group: str, start: datetime.datetime | None = None):
    var_map = ERA5_SFLUX_MAPPING[group]
    if group in ["prc", "rad"]:
        grib_ds = stack_step_time(grib_ds, start=start)
    if "sh2" in var_map:
        grib_ds = grib_ds.rename({"msl": "sp"})
        grib_ds = compute_spfh(grib_ds)
        grib_ds = grib_ds.rename({"sp": "msl"})

    datasets = [get_sflux_ds(grib_ds, g, s) for g, s in var_map.items()]
    merged = xr.merge(datasets, compat="override")

    return merged


def _get_mars(file_by_var: dict[str, Path], group: str, out_grid: dict | None = None):
    var_map = MARS_SFLUX_MAPPING[group]
    is_accumulated = group in ["prc", "rad"]

    def load_var(path: Path) -> xr.Dataset:
        ds = open_meteo_file(path)
        if out_grid is not None:
            from ._convert import regrid_dataset
            ds = regrid_dataset(ds, out_grid=out_grid)
        return ds

    if group == "air" and "sh2" not in file_by_var:
        logger.info("'sh2' file not found, computing from '2d' and 'sp'")
        ds_2d = load_var(file_by_var["2d"])
        ds_psr = load_var(file_by_var["sp"])
        merged = xr.merge([ds_2d, ds_psr], compat="override")
        sh2_ds = compute_spfh(merged)[["sh2"]]
        del ds_2d, ds_psr, merged

    datasets_ = []
    for grib_var, schism_var in var_map.items():
        if grib_var == "sh2" and "sh2" not in file_by_var:
            grib_ds = sh2_ds
        else:
            grib_ds = load_var(file_by_var[grib_var])
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
        if grib_var == "tp":
            ds[schism_var] = ds[schism_var] / 3600 * 1000 # convert from depth in metres of water equivalent to kg/m²/s
        datasets_.append(ds)
    merged = xr.merge(datasets_,compat="override")
    return merged


def check_required_variables(ds: xr.Dataset, group: str):
    required = ERA5_REQUIRED_VARS.get(group, set())
    missing = required - set(ds.variables)
    if missing:
        raise ValueError(f"Missing required variables for '{group}': {missing}")


def _write_sflux(schism_ds: xr.Dataset, filename: Path, overwrite: bool) -> None:
    base_date = schism_ds.time.attrs["base_date"]
    encoding = {
        "time": {
            "units": f"days since {base_date[0]}-{base_date[1]:02d}-{base_date[2]:02d}",
            "dtype": "float32",
        }
    }
    write_file(schism_ds, filename, overwrite=overwrite, encoding=encoding)

    # add simple text file schism_input.txt in the output directory (see SCHISM manual)
    schism_input_file = filename.parent / "sflux_inputs.txt"
    if overwrite or not schism_input_file.exists():
        schism_input_file.write_text("&sflux_inputs\n/\n")


def _era5_sflux_stem(stem: str, slug: str) -> str:
    # era5_[{in_slug}_]{start}_{duration}_{kind} -> era5_{out_slug}_{start}_{duration}_{kind}
    m = re.match(r"^era5_(?:[^_]+_)?(\d{8}_.+)$", stem)
    return f"era5_{slug}_{m.group(1)}" if m else f"{stem}_{slug}"


def era5_to_sflux(
    file: Path,
    group: str,
    output_dir: Path,
    overwrite: bool,
    grid: dict,
    mir_cache_path: Path | None = None,
) -> None:
    from ._convert import regrid_dataset

    if mir_cache_path is not None:
        os.environ.setdefault("MIR_CACHE_PATH", str(mir_cache_path))

    filename = output_dir / f"sflux_{_era5_sflux_stem(file.stem, grid_slug(grid))}_{group}.nc"
    if filename.exists() and not overwrite:
        raise FileExistsError(f"{filename} already exists")
    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    grib_ds = open_meteo_file(file)
    check_required_variables(grib_ds, group)
    grib_ds = grib_ds[sorted(ERA5_REQUIRED_VARS[group])]
    grib_ds = regrid_dataset(grib_ds, out_grid=grid)
    ensure_structured_latlon(grib_ds, str(file))

    grib_ds = auto_pad_lon(grib_ds, method_longitude="auto")

    # request start date from the era5_{grid}_{start}_{duration}_{kind} naming
    m = re.match(r"^era5_(?:[^_]+_)?(\d{8})_", file.stem)
    start = datetime.datetime.strptime(m.group(1), "%Y%m%d") if m else None

    schism_ds = _get_era5(grib_ds, group, start=start)
    _write_sflux(schism_ds, filename, overwrite=overwrite)


def _find_var_file(input_dir: Path, var: str, start_date: datetime.datetime, tag: str) -> Path | None:
    matches = sorted(
        p
        for p in input_dir.rglob(f"*_{start_date:%Y%m%d}_{tag}_{var}.*")
        if p.is_file() and p.suffix.lower() in GRIB_SUFFIXES | {".nc"}
    )
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous input files for variable '{var}': {[str(m) for m in matches]}. "
            "Keep a single grid per directory or pass a more specific --input-dir."
        )
    return matches[0] if matches else None


def mars_to_sflux(
    group: str,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    input_dir: Path,
    output_dir: Path,
    overwrite: bool,
    out_grid: dict | None = None,
    mir_cache_path: Path | None = None,
) -> None:
    """
    Convert per-variable MARS GRIB/NetCDF files to SCHISM sflux NetCDF.

    Input files are discovered recursively under ``input_dir`` by their
    ``{grid}_{start}_{duration}_{variable}`` naming convention (as produced by
    ``meteo download mars``, optionally regridded with ``meteo convert regrid``).
    The grid is inferred from the files themselves: native reduced Gaussian files
    (e.g. O1280) are regridded on the fly with MIR onto ``out_grid`` (default: the
    matching regular Gaussian grid, F1280 for O1280); files already on a structured
    latitude/longitude grid are used as is, or regridded when ``out_grid`` is given.

    The files needed per group are:
        * For 'air': [msl, u10, v10, t2m, sh2 (or 2d+sp)]
        * For 'rad': [ssrd, strd]
        * For 'prc': [tp]

    Parameters
    ----------
    group : str
        Variable group: 'air', 'rad', or 'prc'.
    start_date : datetime.datetime
        Start date of the downloaded data.
    end_date : datetime.datetime
        End of the downloaded data, **exclusive**.
    input_dir : Path
        Directory scanned (recursively) for the input files.
    output_dir : Path
        Output directory for sflux NetCDF files.
    overwrite : bool
        Whether to overwrite existing output files.
    out_grid : dict, optional
        Rectilinear MIR output grid for on-the-fly regridding (e.g. ``{"grid": "F1280"}``
        or ``{"grid": [0.25, 0.25]}``). Defaults to the regular Gaussian grid matching
        the input resolution when the input is not structured; no regridding otherwise.
    mir_cache_path : Path, optional
        Cache directory for MIR interpolation weights.
    """
    if mir_cache_path is not None:
        os.environ.setdefault("MIR_CACHE_PATH", str(mir_cache_path))

    tag = compute_duration_tag(start_date, end_date)
    file_by_var = {}
    missing = []
    for var in MARS_SFLUX_MAPPING[group]:
        fpath = _find_var_file(input_dir, var, start_date, tag)
        if fpath is None:
            missing.append(var)
        else:
            file_by_var[var] = fpath

    if "sh2" in missing:
        logger.info("'sh2' file not found, will attempt to compute from '2d' and 'sp'")
        missing.remove("sh2")
        for fallback_var in ["2d", "sp"]:
            fb_path = _find_var_file(input_dir, fallback_var, start_date, tag)
            if fb_path is None:
                raise FileNotFoundError(
                    f"Neither 'sh2' nor '{fallback_var}' found under {input_dir}. "
                    "Need either 'sh2' directly or both '2d' and 'sp' to compute it."
                )
            file_by_var[fallback_var] = fb_path

    if missing:
        raise FileNotFoundError(f"Missing files for group '{group}' under {input_dir}: {missing}")

    logger.debug("Saving to: %s", output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    first_file = next(iter(file_by_var.values()))
    probe = open_meteo_file(first_file)
    grid_spec = infer_grid(probe)
    lon_name, lat_name = detect_name(probe, "longitude"), detect_name(probe, "latitude")
    structured = {lon_name, lat_name} <= set(probe.dims)
    del probe
    if out_grid is None and not structured:
        # reduced Gaussian input (e.g. O1280): regrid on the fly to the matching regular grid
        if grid_spec is None:
            raise ValueError(f"Could not infer the grid of {first_file}; regrid it first with `meteo convert regrid`.")
        out_grid = default_out_grid(grid_spec)
    slug = grid_slug(out_grid or grid_spec) if (out_grid or grid_spec) else "grid"

    schism_ds = _get_mars(file_by_var, group, out_grid=out_grid)
    filename = output_dir / f"sflux_{slug}_{start_date:%Y%m%d}_{tag}_{group}.nc"
    _write_sflux(schism_ds, filename, overwrite=overwrite)
