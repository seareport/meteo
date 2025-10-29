from __future__ import annotations

import os
import pathlib
import platform
from typing import Annotated

import platformdirs

from cyclopts import Parameter
from cyclopts import validators
from cyclopts.types import ResolvedDirectory
from cyclopts.types import ResolvedExistingDirectory

from ._literals import L_Months
from ._literals import L_ECMWF_Variables
from ._utils import get_grib_path

_HOSTNAME = platform.node()

# mutable variables during initialization
# We will use CONSTANTS after we initialize them
_default_cache_dir: pathlib.Path
_default_ecmwf_operational_dir: pathlib.Path

if "meluxina" in _HOSTNAME:
    _GROUP_ID = os.getgroups()[-1]
    _PROJECT_DIR = pathlib.Path(f"/project/home/p{_GROUP_ID}")
    _SCRATCH_DIR = pathlib.Path(f"/project/scratch/p{_GROUP_ID}")
    _default_cache_dir = _SCRATCH_DIR / "cache"
    _default_ecmwf_operational_dir = _PROJECT_DIR / "02_meteo/ecmwf/operational/"
else:
    _default_cache_dir = platformdirs.user_cache_path()
    _default_ecmwf_operational_dir = pathlib.Path(os.environ.get("ECMWF_OPERATIONAL_DIR", "."))

_DEFAULT_ECMWF_OPERATIONAL_DIR = _default_ecmwf_operational_dir
_DEFAULT_CACHE_DIR = _default_cache_dir
_DEFAULT_CACHE_MIR_DIR = _DEFAULT_CACHE_DIR / "mir"
_DEFAULT_CACHE_METVIEW_DIR = _DEFAULT_CACHE_DIR / "metview"

_YEAR_VALIDATOR = Parameter(validator=validators.Number(gte=1900))


def cli_download_o1280(
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    variable: L_ECMWF_Variables,
    output_dir: ResolvedDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR,
    no_steps: int = 12,
) -> None:
    """
    Download ECMWF operational forecast data on the O1280 octahedral Gaussian grid.

    Downloads high-resolution (~9km) ECMWF operational forecast data in GRIB format
    for a specified month. Requires ECMWF API credentials in `~/.ecmwfapirc`.

    Parameters
    ----------
    year : int
        Year to download (must be >= 1900).
    month : int
        Month to download (1-12).
    variable : str
        ECMWF variable code. Supported variables include: 'msl' (mean sea level
        pressure), 'u10'/'v10' (10m wind components), 't2m' (2m temperature),
        'sh2' (2m specific humidity), 'ssrd'/'strd' (surface radiation), 'tp'
        (total precipitation).
    output_dir : Path, default: system-specific
        Output directory for downloaded files. Data is saved to an 'O1280'
        subdirectory within this path. Defaults to a platform-specific location.
    no_steps : int, default: 12
        Number of forecast time steps to download. Automatically incremented by
        one for accumulated variables (e.g., precipitation, radiation).

    Notes
    -----
    Output files follow a standardized naming convention within the O1280 subdirectory.
    For example, downloading mean sea level pressure for January 2024 creates:
    ``{output_dir}/O1280/grib/2024/o.2024.01.msl.grib``
    """
    from meteo._download import download_o1280_month

    download_o1280_month(
        variable=variable,
        year=year,
        month=month,
        output_path=output_dir / "O1280",
        no_steps=no_steps,
    )


def cli_convert_o1280_to_f1280(
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    variable: L_ECMWF_Variables,
    ecmwf_operational_dir: ResolvedExistingDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR,
    mir_cache_path: ResolvedDirectory = _DEFAULT_CACHE_MIR_DIR,
    metview_tmp_path: ResolvedDirectory = _DEFAULT_CACHE_METVIEW_DIR,
    mars_maxforks: int = 16,
) -> None:
    """
    Convert GRIB files from O1280 (octahedral) to F1280 (full) Gaussian grid.

    Regrid ECMWF operational forecast data from the O1280 octahedral Gaussian
    grid to the F1280 full Gaussian grid using Metview. Both grids have similar
    spatial resolution (~9km), but the F1280 regular structure may be preferred
    for certain applications. Requires Metview to be installed.

    Parameters
    ----------
    year : int
        Year of the data to convert (must be >= 1900).
    month : int
        Month of the data to convert (1-12).
    variable : str
        ECMWF variable code. Supported variables include: 'msl' (mean sea level
        pressure), 'u10'/'v10' (10m wind components), 't2m' (2m temperature),
        'sh2' (2m specific humidity), 'ssrd'/'strd' (surface radiation), 'tp'
        (total precipitation).
    ecmwf_operational_dir : Path, default: system-specific
        Base directory containing 'O1280' (input) and 'F1280' (output) subdirectories.
        The O1280 directory must exist and contain the input GRIB file.
    mir_cache_path : Path, default: system cache
        Cache directory for MIR (Meteorological Interpolation and Regridding)
        operations to speed up repeated conversions.
    metview_tmp_path : Path, default: system cache
        Temporary directory for Metview operations.
    mars_maxforks : int, default: 16
        Maximum number of parallel processes for MARS/MIR operations.

    Notes
    -----
    Input and output file paths are determined automatically based on the variable,
    year, and month. For example, converting mean sea level pressure for January 2024:

    - Input: ``{ecmwf_operational_dir}/O1280/grib/2024/o.2024.01.msl.grib``
    - Output: ``{ecmwf_operational_dir}/F1280/grib/2024/f.2024.01.msl.grib``

    The output F1280 directory is created if it doesn't exist.
    """
    from meteo._convert import o1280_to_f1280

    o1280_path = ecmwf_operational_dir / "O1280" / get_grib_path(variable, year, month, "O1280")
    f1280_path = ecmwf_operational_dir / "F1280" / get_grib_path(variable, year, month, "F1280")
    o1280_to_f1280(
        o1280_path=o1280_path,
        f1280_path=f1280_path,
        mir_cache_path=mir_cache_path,
        metview_tmp_path=metview_tmp_path,
        mars_maxforks=mars_maxforks,
    )


def cli_convert_f1280_to_sflux():
    """ Convert F1280 grib files sflux netcdf files """


def cli_download_era5():
    """ Download ERA5 from ECMWF using ECMWFAPI """


def cli_convert_era5_to_sflux():
    """ Convert ERA5 to sflux format """


