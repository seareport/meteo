#! /usr/bin/env python
from __future__ import annotations

import datetime
import logging
import pathlib
from typing import get_args

from ._constants import ECMWF_VARIABLE_CODES
from ._constants import ERA5_COLLECTION_NATIVE
from ._constants import ERA5_COLLECTION_REGULAR
from ._constants import ERA5_NATIVE_GRID
from ._constants import ERA5_PARAM_IDS
from ._literals import L_ECMWF_Variables
from ._literals import L_ERA5_Avg_Variables
from ._literals import L_ERA5_Instant_Variables
from ._literals import L_ERA5_Variables
from ._utils import compute_duration_tag
from ._utils import get_grib_name
from ._utils import grid_slug
from ._utils import inclusive_to_exclusive
from ._utils import parse_grid

logger = logging.getLogger(__name__)

O1280_NO_STEPS = 12


def download_mars(
    variable: L_ECMWF_Variables,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    output_dir: pathlib.Path,
    grid: str = "O1280",
) -> None:
    logger.debug("Downloading %s from MARS: %s", grid, locals())
    from ecmwfapi import ECMWFService

    end_date_inclusive = inclusive_to_exclusive(end_date)
    if end_date_inclusive < start_date:
        raise ValueError(f"Date range is empty: {start_date} to {end_date} (exclusive)")

    filepath = output_dir / get_grib_name(variable, start_date, end_date, grid)
    logger.debug("Saving to: %s", filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    code, is_accumulated = ECMWF_VARIABLE_CODES[variable]
    # 12h forecasts from 00/12 UTC; accumulated variables need one extra step to difference
    no_steps = O1280_NO_STEPS + 1 if is_accumulated else O1280_NO_STEPS
    step = "/".join(map(str, range(no_steps)))

    server = ECMWFService("mars")
    server.execute(
        {
            'stream'    : "oper",
            'levtype'   : "sfc",
            "param"     : f"{code}",
            'expver'    : "1",
            'step'      : step,
            'area'      : "90.0/-180.0/-90.0/180.0",
            'grid'      : grid,
            'date'      : f"{start_date:%Y%m%d}/to/{end_date_inclusive:%Y%m%d}",
            'time'      : "00/12",
            'type'      : "fc",
            'class'     : "od",
            'accuracy'  : "av",
            "packing"   : "av",
        },
        str(filepath),
    )


def get_era5_name(start: datetime.datetime, end: datetime.datetime, step_type: str, grid) -> str:
    return f"era5_{grid_slug({'grid': grid})}_{start:%Y%m%d}_{compute_duration_tag(start, end)}_{step_type}.nc"


def _era5_native_requests(
    instant_vars: list[str],
    avg_vars: list[str],
    start_date: datetime.datetime,
    last_date: datetime.datetime,
) -> dict[str, dict]:
    # MARS-style requests against reanalysis-era5-complete, served on the native N320 reduced
    # Gaussian grid (no 'grid' keyword: CDS era5-complete only serves the archived grid).
    base = {
        "class": "ea",
        "expver": "1",
        "stream": "oper",
        "levtype": "sfc",
        "grid": "N320"
    }
    requests = {}
    if avg_vars:
        # 06/18 UTC forecasts (steps 1-12), starting one day early so the first hours are covered
        avg_start =  start_date - datetime.timedelta(days=1)
        requests["avg"] = {
            **base,
            "type": "fc",
            "date": f"{avg_start:%Y-%m-%d}/to/{last_date:%Y-%m-%d}",
            "time": "06/18",
            "step": "1/to/12/by/1",
            "param": "/".join(str(ERA5_PARAM_IDS[v]) for v in avg_vars),
        }
    if instant_vars:
        requests["instant"] = {
            **base,
            "type": "an",
            "date": f"{start_date:%Y-%m-%d}/to/{last_date:%Y-%m-%d}",
            "time": "00/to/23/by/1",
            "param": "/".join(str(ERA5_PARAM_IDS[v]) for v in instant_vars),
        }
    return requests


def _era5_regridded_requests(
    instant_vars: list[str],
    avg_vars: list[str],
    start_date: datetime.datetime,
    last_date: datetime.datetime,
    grid: list[float],
) -> dict[str, dict]:
    # CDS requests against reanalysis-era5-single-levels, interpolated to a regular lat/lon grid.
    base = {
        "product_type": "reanalysis",
        "data_format": "grib",
        "download_format": "unarchived",
        "date": f"{start_date.date()}/{last_date.date()}",
        "time": [f"{h:02d}:00" for h in range(24)],
        "grid": grid,
    }
    requests = {}
    if avg_vars:
        requests["avg"] = {**base, "variable": avg_vars}
    if instant_vars:
        requests["instant"] = {**base, "variable": instant_vars}
    return requests


def download_era5(
    variable: L_ERA5_Variables,
    start_date: datetime.datetime,
    end_date: datetime.datetime | None,
    output_dir: pathlib.Path,
    grid: str = ERA5_NATIVE_GRID,
) -> None:
    """
    Download ERA5 surface reanalysis data from the Copernicus CDS with ``earthkit-data``.

    Submits one request per ``stepType`` group (``instant`` and ``avg``)
    Output is one NetCDF per group.

    Parameters
    ----------
    variable : L_ERA5_Variables
        ERA5 variable name(s) to download. Variables are automatically split
        into ``instant`` and ``avg`` sub-requests based on their ``stepType``.
    start_date : datetime.datetime
        First day of the requested period.
    end_date : datetime.datetime
        End of the requested period, **exclusive**. Data is downloaded for
        all days in ``[start_date, end_date)``, i.e. up to but not including
        ``end_date``. Passed directly to the ECMWF API ``date`` field.
    output_dir : pathlib.Path
        Directory where NetCDF files are written. Created if it does not exist.
    grid : str
        ``N320`` (the default - the native archived grid, from ``reanalysis-era5-complete``;
        the only Gaussian grid served by CDS) or a resolution in degrees (e.g. ``0.25``)
        for regular lat/lon output from ``reanalysis-era5-single-levels``.

    Raises
    ------
    ValueError
        If the date range is empty (``end_date <= start_date``).
    """
    import earthkit.data as ekd
    from concurrent.futures import ThreadPoolExecutor

    output_dir.mkdir(parents=True, exist_ok=True)
    grid_value = parse_grid(grid)["grid"]
    native = isinstance(grid_value, str)
    if native and grid_value != ERA5_NATIVE_GRID:
        raise ValueError(
            f"reanalysis-era5-complete only serves ERA5 on its native grid ({ERA5_NATIVE_GRID}); "
            f"got {grid_value!r}. Use a resolution in degrees (e.g. '0.25') for a regular lat/lon grid."
        )
    collection_id = ERA5_COLLECTION_NATIVE if native else ERA5_COLLECTION_REGULAR

    last_date = inclusive_to_exclusive(end_date)
    if last_date < start_date:
        raise ValueError(f"Date range is empty: {start_date} to {end_date} (exclusive)")

    avg_vars = [v for v in variable if v in get_args(L_ERA5_Avg_Variables)]
    instant_vars = [v for v in variable if v in get_args(L_ERA5_Instant_Variables)]

    if native:
        requests = _era5_native_requests(instant_vars, avg_vars, start_date, last_date)
    else:
        requests = _era5_regridded_requests(instant_vars, avg_vars, start_date, last_date, grid_value)

    results = {}
    for step_type, request in requests.items():
        logger.debug("Submitting %s/%s: %s", collection_id, step_type, request)
        results[step_type] = ekd.from_source_lazily("cds", collection_id, request=request)

    def _retrieve_and_save(step_type: str, ds) -> pathlib.Path:
        target = output_dir / get_era5_name(start_date, end_date, step_type, grid_value)
        logger.info("Converting %s -> %s", step_type, target)
        ds.to_xarray().to_netcdf(target)
        return target

    with ThreadPoolExecutor(max_workers=len(results)) as pool:
        futures = [pool.submit(_retrieve_and_save, st, ds) for st, ds in results.items()]
        for future in futures:
            future.result()
