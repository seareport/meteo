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
from ._utils import date_range_to_ymd
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
    start_date: datetime.date,
    duration: str,
    output_dir: pathlib.Path,
) -> None:
    logger.debug("Downloading ERA5: %s", locals())
    import datetime
    from ecmwf.datastores import Client
    from ._utils import parse_iso_duration

    output_dir.mkdir(parents=True, exist_ok=True)
    client = Client()
    collection_id = "reanalysis-era5-single-levels"

    _start_date = datetime.datetime.strptime(start_date, "%Y%m%d").date()
    _end_date = parse_iso_duration(duration, _start_date) - datetime.timedelta(days=1)
    if _end_date < _start_date:
        raise ValueError(f"Date range is empty: {_start_date} to {parse_iso_duration(duration, _start_date)} (exclusive)")

    request = {
        "product_type": ["reanalysis"],
        "data_format": "grib",
        "download_format": "unarchived",
        "date" : f"{_start_date}/{_end_date}",
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

    for step_type, remote in remotes:
        target = output_dir / f"era5_{_start_date:%Y%m%d}_{duration}_{step_type}.grib"
        logger.info("Waiting & downloading %s -> %s", step_type, target)
        remote.download(str(target))  # blocks until this job is done
