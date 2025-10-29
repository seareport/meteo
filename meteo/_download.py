#! /usr/bin/env python
from __future__ import annotations
import calendar
import logging
import pathlib
import sys

from ._constants import ECMWF_VARIABLE_CODES
from ._literals import L_Grids
from ._literals import L_Months
from ._literals import L_ECMWF_Variables
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
