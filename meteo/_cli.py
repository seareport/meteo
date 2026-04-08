from __future__ import annotations

import datetime
import os
import pathlib
import platform
from pathlib import Path
from typing import Annotated
from typing import get_args

import platformdirs
from cyclopts import Group
from cyclopts import Parameter
from cyclopts import validators
from cyclopts.types import ResolvedDirectory
from cyclopts.types import ResolvedExistingDirectory

from ._literals import L_6Hours
from ._literals import L_CMEMS_export_format
from ._literals import L_Days
from ._literals import L_ECMWF_Variables
from ._literals import L_ERA5_Variables
from ._literals import L_Months
from ._literals import L_sflux_groups
from ._literals import Lon_Convention
from ._literals import PadMethodLat
from ._literals import PadMethodLon
from ._literals import PadSideLat
from ._utils import get_grib_path

_HOSTNAME = platform.node()

# mutable variables during initialization
# We will use CONSTANTS after we initialize them
_default_cache_dir: pathlib.Path
_default_ecmwf_dir: pathlib.Path
_default_hycom_dir: pathlib.Path

if "meluxina" in _HOSTNAME:
    _GROUP_ID = os.getgroups()[-1]
    _PROJECT_DIR = pathlib.Path(f"/project/home/p{_GROUP_ID}")
    _SCRATCH_DIR = pathlib.Path(f"/project/scratch/p{_GROUP_ID}")
    _default_cache_dir = _SCRATCH_DIR / "cache"
    _default_ecmwf_dir = _PROJECT_DIR / "02_meteo/ecmwf/"
    _default_ecmwf_operational_dir = _PROJECT_DIR / "02_meteo/ope_ecmwf/"
    _default_hycom_dir = _PROJECT_DIR / "02_meteo/hycom/"
    _default_cmems_dir = _PROJECT_DIR / "02_meteo/cmems/"
    _default_era5_dir = _PROJECT_DIR / "02_meteo/era5/"
else:
    _default_cache_dir = platformdirs.user_cache_path()
    _default_ecmwf_dir = pathlib.Path(os.environ.get("ECMWF_DIR", "ecmwf"))
    _default_ecmwf_operational_dir = pathlib.Path(os.environ.get("ECMWF_DIR", "ope_ecmwf"))
    _default_hycom_dir = pathlib.Path(os.environ.get("HYCOM_DIR", "hycom"))
    _default_cmems_dir = pathlib.Path(os.environ.get("CMEMS_DIR", "cmems"))
    _default_era5_dir = pathlib.Path(os.environ.get("ERA5_DIR", "era5"))

_DEFAULT_ERA5_DIR = _default_era5_dir
_DEFAULT_ECMWF_DIR = _default_ecmwf_dir
_DEFAULT_HYCOM_DIR = _default_hycom_dir
_DEFAULT_ECMWF_OPERATIONAL_DIR = _default_ecmwf_operational_dir
_DEFAULT_CMEMS_DIR = _default_cmems_dir
_DEFAULT_CACHE_DIR = _default_cache_dir
_DEFAULT_CACHE_MIR_DIR = _DEFAULT_CACHE_DIR / "mir"
_DEFAULT_CACHE_METVIEW_DIR = _DEFAULT_CACHE_DIR / "metview"

_YEAR_VALIDATOR = Parameter(validator=validators.Number(gte=1900))
_TIME_RANGE_VALIDATOR = Group("Time range", validator=validators.MutuallyExclusive())

def cli_download_o1280(
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    variable: L_ECMWF_Variables,
    output_dir: ResolvedDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR / "O1280",
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
    from meteo._ecmwf import download_o1280_month

    download_o1280_month(
        variable=variable,
        year=year,
        month=month,
        output_path=output_dir,
        no_steps=no_steps,
    )


def cli_convert_normalize_lon(
    input_file: pathlib.Path,
    output_file: pathlib.Path,
    *,
    longitude_convention: Lon_Convention = "180",
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
) -> None:
    """Normalize longitude to [-180°, 180°] or [0°, 360°].

    Parameters
    ----------
    input_file:
        Path to the input dataset file (e.g., NetCDF, zarr).
    output_file:
        Path to save the normalized dataset.
    longitude_convention:
        Determines the longitude convention; [-180°, 180°] vs [0°, 360°]
    overwrite:
        Whether to overwrite the output file if it already exists.
    """
    from ._convert import convert_normalize_longitude

    convert_normalize_longitude(
        input_file = input_file,
        output_file = output_file,
        longitude_convention=longitude_convention,
        overwrite=overwrite
    )


def cli_convert_pad(
    input_file: pathlib.Path,
    output_file: pathlib.Path,
    *,
    pad_longitude: Annotated[bool, Parameter(negative=False)] = False,
    pad_latitude: Annotated[bool, Parameter(negative=False)] = False,
    pad_method_longitude: Annotated[PadMethodLon, Parameter(show_choices=False)] = "auto",
    pad_method_latitude: PadMethodLat = "fade",
    pad_side_latitude: PadSideLat = "north",
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
) -> None:
    """add padding values around the borders of the dataset.

    Operations include:
    - Longitude padding wraps values around the antimeridian (±180° or 0°/360°)
    - Latitude padding extends coverage to include poles (-90° to 90°)

    Parameters
    ----------
    input_file:
        Path to the input dataset file (e.g., NetCDF, zarr).
    output_file:
        Path to save the normalized dataset.
    pad_longitude:
        Whether to pad longitude coordinates to wrap around the antimeridian.
    pad_latitude:
        Whether to pad latitude coordinates to include the poles.
    pad_method_longitude:
        Method for padding longitudes ('auto' or positive integer).
    pad_method_latitude:
        Method for padding latitudes
    pad_side_latitude:
        Whether to pad north or south pole.
    overwrite:
        Whether to overwrite the output file if it already exists.

    Notes
    -----
    For the longitude padding the dataset is automatically converted to [-180°, 180°]
    For the latitude padding, the extremities are strictly set to [-90°, 90°]. The extrapolation methods for latitudes are:
        `median`: Fill with `nanmedian` of boundary row.
        `fade`: we blend the boundary row into `nanmedian` towards the poles
    """
    from ._convert import convert_pad

    convert_pad(
        input_file=input_file,
        output_file=output_file,
        pad_longitude=pad_longitude,
        pad_latitude=pad_latitude,
        method_longitude=pad_method_longitude,
        method_latitude=pad_method_latitude,
        side=pad_side_latitude,
        overwrite=overwrite
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


def cli_convert_f1280_to_sflux(
    *,
    group: L_sflux_groups,
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    f1280_dir: ResolvedExistingDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR / "F1280",
    output_dir: Path = _DEFAULT_ECMWF_OPERATIONAL_DIR / "F1280" / "sflux",
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
):
    """
    Convert F1280 GRIB files to SCHISM sflux files.

    By specifying the variable `group` (air, rad, prc), the `year` and `month`,
    the corresponding F1280 GRIB files necessary for group are mapped and merged into a single NetCDF.

    The program returns an error if any of the required files is missing.

    Parameters
    ----------
    group : str
        Variable group to convert: 'air', 'rad', or 'prc'.
    year : int
        Year of the data.
    month : int
        Month of the data (1-12).
    f1280_dir : Path
        Base F1280 directory containing grib/{year}/ subdirectories.
    output_dir : Path
        Output directory for sflux NetCDF files.
    overwrite : bool
        Whether to overwrite existing output files.
    """
    from meteo._sflux import f1280_to_sflux

    f1280_to_sflux(
        group=group,
        year=year,
        month=month,
        f1280_dir=f1280_dir,
        output_dir=output_dir,
        overwrite=overwrite,
    )


def cli_download_era5(
    *,
    start_date: datetime.datetime,
    duration: Annotated[str, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    end_date: Annotated[datetime.datetime, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    variable: Annotated[L_ERA5_Variables, Parameter(show_choices=True)] = None,
    output_dir: ResolvedDirectory = _DEFAULT_ERA5_DIR,
) -> None:
    """
    Download ERA5 from ECMWF using the
    [new `ecmwf-datastores-client` API](https://ecmwf.github.io/ecmwf-datastores-client/)
    (async downloads)

    The ERA5 request downloads by default variables for hydrodynamic baroclinic simulations,
    divided in two groups of **different `stepType`** values:

    | `stepType`  | Variables                         | Time dimension                  |
    |------------|-----------------------------------|----------------------------------|
    | `instant`  | `u10`, `v10`, `d2m`, `t2m`, `msl` | Hourly (`time` of length 720) |
    | `avg`      | `avg_tprate`, `avg_sdswrf`, `avg_sdlwrf` | 12-hour forecast steps from twice-daily reference times (61 `time` × 12 `step`) |

    The request is thus split into two sub-requests to avoid having a unique dataset with mixed `stepType`, inducing errors when opening the full dataset with xarray.

    Time range
    ----------
     * ``--start-date`` is the first day of data to download.
     * ``--end-date`` is **exclusive**: data up to (but not including) that date is downloaded.
     * All hourly timesteps (00:00–23:00) of each included day are retrieved.
     * Instead of ``--end-date``, you can pass ``--duration`` as an ISO 8601 string. The exclusive end date is then computed as ``start_date + duration``.

    Examples
    ---------
    The following command is the same:
    ```
    meteo download era5 --start-date 20250101 --end-date 20250201       # all of January 2025
    meteo download era5 --start-date 20250101 --duration P1M            # same: 2025-01-01 to 2025-01-31 23:00:00
    ```
    and creates 2 output files:
     * ``{output_dir}/era5_20250101_P1M_avg.grib``
     * ``{output_dir}/era5_20250101_P1M_instant.grib``

    With `output_dir` = `_DEFAULT_ERA5_DIR` a machine specific directory that can be changed with the `--output_dir` flag.

    Parameters
    ----------
    start_date : datetime.datetime
        Start date in YYYYMMDD format
    end_date : datetime.datetime
        Last day of data to download, **exclusive** (YYYYMMDD format).
        Cannot be called if ``duration`` is provided.
    duration : str
        ISO 8601 string for period to download (e.g., `PnD`, `PnW`, `PnM`, `PnY` and combinations like `P1M15D`).
        Cannot be called if ``end_date`` is provided.
    variable : str
        ERA5 variables, by default all are downloaded.
    output_dir : Path, default: system-specific
        Output directory for downloaded files.
        Defaults to `_DEFAULT_ERA5_DIR` which is a platform-specific location.
    """
    if variable is None:
        variable = list(get_args(L_ERA5_Variables))
    from meteo._ecmwf import download_era5
    from meteo._utils import compute_end_date

    if duration:
        end_date = compute_end_date(start_date, duration)

    download_era5(
        variable=variable,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def cli_convert_era5_to_sflux(
    *,
    file: Annotated[Path, Parameter(validator=validators.Path(exists=True, file_okay=True, dir_okay=False))],
    group: L_sflux_groups,
    output_dir: Path = _DEFAULT_ERA5_DIR / "sflux",
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
):
    """
    Convert ERA5 GRIB files to SCHISM sflux format.

    ERA5 GRIB files mix instant and averaged variables with incompatible time axes, so they must be opened separately by stepType before conversion.
    Each argument expects a NetCDF file already filtered and normalized for its variable group.

    Note: This implementation assumes global ERA5 input data intended for interpolation onto global models. Longitude is padded by default (cyclic wrap-around) to ensure periodic continuity across the -180°/180° boundary.

    Parameters
    ----------
    file: Path
        Path to the input GRIB file containing ERA5 data. The file should contain only the relevant variables for either the `air`, `rad`, or `prc` group, and should be preprocessed to have consistent longitude and latitude coordinates.
        * For `air` variables (`u10`, `v10`, `d2m`, `t2m`, `msl`), the file should contain hourly data with `stepType=instant`.
        * For `rad` variables (`avg_sdswrf`, `avg_sdlwrf`), the file should contain 12-hourly averaged data with `stepType=avg`.
        * For `prc` variable (`avg_tprate`), the file should contain 12-hourly averaged data with `stepType=avg`.
    group: str
        Variable group to convert. Must be one of 'air', 'rad', or 'prc'.
    output_dir: Path
        Output directory. Daily files are written as `sflux_{air,rad,prc}_1.XXXX.nc`
        Defaults to `_DEFAULT_ERA5_DIR/sflux` which is a platform-specific location.
    overwrite: bool
        Whether to overwrite the output file if it already exists.
    """

    from meteo._sflux import era5_to_sflux

    era5_to_sflux(
        file=file,
        group=group,
        output_dir=output_dir,
        overwrite=overwrite,
    )


def cli_hycom(
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    day: Annotated[L_Days, Parameter(show_choices=False)],
    *,
    output_dir: Path = _DEFAULT_HYCOM_DIR,
    normalize: bool = True
):
    """
    Download HYCOM data.

    Parameters
    ----------
    year : int
        Year to download (must be >= 1900).
    month : int
        Month to download (1-12).
    day : int
        Day to download (1-31).
    output_dir : Path, default: system-specific
        Output directory for downloaded files.
        Defaults to `_DEFAULT_HYCOM_DIR` which is a platform-specific location.
    normalize: bool
        Convert HYCOM longitude coordinates to the 0-360° convention

    Notes
    -----
    This function is based on the DownloadHycom Class in pyschism: https://github.com/schism-dev/pyschism/blob/44061ac6c594417d3d7e5c624ab03d76a569cb05/pyschism/forcing/hycom/hycom2schism.py#L778
    Output files are saved by default in the `_DEFAULT_HYCOM_DIR` directory that can be changed with the --output_dir flag.
    For example, downloading HYCOM for 11 January 2024 creates:
    ``{output_dir}/hycom_20240111.nc``

    More info on the HYCOM model: https://www.hycom.org
    """
    from meteo._hycom import download_hycom

    download_hycom(
        year=year,
        month=month,
        day=day,
        output_dir=output_dir,
        normalize=normalize
    )


def cli_cmems(
    year: Annotated[int, _YEAR_VALIDATOR],
    month: L_Months,
    day: Annotated[L_Days, Parameter(show_choices=False)],
    hour: L_6Hours = 0,
    *,
    dataset: str = "cmems_mod_glo_phy",
    output_dir: Path = _DEFAULT_CMEMS_DIR,
    output_format: L_CMEMS_export_format = "cmems"
):
    """
    Download CMEMS data using the `copernicusmarine` python API

    Parameters
    ----------
    year : int
        Year to download (must be >= 1900).
    month : int
        Month to download (1-12).
    day : int
        Day to download (1-31).
    hour : int
        Hour to download (0/6/12 or 18)
    dataset : str
        dataset to download from the Copernicus Marine Data Store.
        For now, only `cmems_mod_glo_phy` is available
    output_dir : Path, default: system-specific
        Output directory for downloaded files.
        Defaults to `_DEFAULT_CMEMS_DIR` which is a platform-specific location.
    output_format : str
        Format of the exported netcdf.
        `hycom` mimics the HYCOM model file format and fits SCHISM hotstart pipeline.

    Notes
    -----
    Many datasets can be downloaded from the Copernicus Marine Data Store.
    For now, only the GLORYSv12 `cmems_mod_glo_phy` Reanalysis and Forecast (1993 - present) are available.

    If the selected date is before 16/09/2025, the Reanalysis product is used; otherwise, the Forecast product is selected.

    If the selected hour is 0, the Daily product is used; otherwise, the 6-Hourly product is used. This rule applies only to forecasts.
    For reanalysis data, the nearest daily value at midnight is retrieved.

    More info on the other products can be found at: https://data.marine.copernicus.eu/product/
    More info on the Python API can be found at: https://help.marine.copernicus.eu/en/collections/9080063-copernicus-marine-toolbox
    """
    from meteo._cmems import download_cmems

    download_cmems(
        year=year,
        month=month,
        day=day,
        hour=hour,
        dataset=dataset,
        output_dir=output_dir,
        output_format=output_format
    )
