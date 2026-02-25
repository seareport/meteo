#! /usr/bin/env python
from __future__ import annotations

import calendar
import datetime
import logging
import pathlib
from typing import get_args

from ._constants import ECMWF_VARIABLE_CODES
from ._literals import L_ECMWF_Variables
from ._literals import L_ERA5_Avg_Variables
from ._literals import L_ERA5_Instant_Variables
from ._literals import L_ERA5_Variables
from ._literals import L_Grids
from ._literals import L_Months
from ._utils import compute_duration_tag
from ._utils import get_grib_path

logger = logging.getLogger(__name__)


def download_o1280_month(
    variable: L_ECMWF_Variables,
    year: int,
    month: L_Months,
    output_path: pathlib.Path,
    no_steps: int = 12,
) -> None:
    logger.debug("Downloading O1280: %s", locals())
    from ecmwfapi import ECMWFService

    filepath = output_path / get_grib_path(variable, year, month, "O1280")
    logger.debug("Saving to: %s", filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    _, no_days_in_month = calendar.monthrange(year, month)
    d1 = f"{year:04d}{month:02d}01"
    d2 = f"{year:04d}{month:02d}{no_days_in_month:2d}"

    code, is_accumulated = ECMWF_VARIABLE_CODES[variable]
    if is_accumulated:
        no_steps += 1
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
            'grid'      : "O1280",
            'date'      : f"{d1}/to/{d2}",
            'time'      : "00/12",
            'type'      : "fc",
            'class'     : "od",
            'accuracy'  : "av",
            "packing"   : "av",
        },
        str(filepath),
    )


def download_era5(
    variable: L_ERA5_Variables,
    start_date: datetime.datetime,
    end_date: datetime.datetime | None,
    output_dir: pathlib.Path,
) -> None:
    """
    Download ERA5 single-level reanalysis data from the ECMWF datastore.

    Submits one async request per ``stepType`` group (``instant`` and ``avg``)
    and blocks until each download completes.

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
        Directory where GRIB files are written. Created if it does not exist.

    Raises
    ------
    ValueError
        If the date range is empty (``end_date <= start_date``).
    """
    logger.debug("Downloading ERA5: %s", locals())
    from ecmwf.datastores import Client
    from meteo._utils import inclusive_to_exclusive

    output_dir.mkdir(parents=True, exist_ok=True)
    client = Client()
    collection_id = "reanalysis-era5-single-levels"

    end_date_exclusive = inclusive_to_exclusive(end_date)
    if end_date_exclusive < start_date:
        raise ValueError(f"Date range is empty: {start_date} to {end_date_exclusive} (exclusive)")

    request = {
        "product_type": ["reanalysis"],
        "data_format": "grib",
        "download_format": "unarchived",
        "date" : f"{start_date.date()}/{end_date_exclusive.date()}",
        "time": [f"{h:02d}:00" for h in range(24)],
    }

    # split by stepType
    avg_vars = [v for v in variable if v in get_args(L_ERA5_Avg_Variables)]
    instant_vars = [v for v in variable if v in get_args(L_ERA5_Instant_Variables)]

    remotes = []
    if avg_vars:
        avg_request = {**request, "variable": avg_vars}
        remotes.append(("avg", client.submit(collection_id, avg_request)))
    if instant_vars:
        instant_request = {**request, "variable": instant_vars}
        remotes.append(("instant", client.submit(collection_id, instant_request)))

    duration = compute_duration_tag(start_date, end_date)
    for step_type, remote in remotes:
        target = output_dir / f"era5_{start_date:%Y%m%d}_{duration}_{step_type}.grib"
        logger.info("Waiting & downloading %s -> %s", step_type, target)
        remote.download(str(target))  # blocks until this job is done
