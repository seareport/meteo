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

_YEAR_VALIDATOR = Parameter(validator=validators.Number(gte=1900))
_TIME_RANGE_VALIDATOR = Group("Time range", validator=validators.MutuallyExclusive())

def cli_download_mars(
    *,
    start_date: datetime.datetime,
    variable: L_ECMWF_Variables,
    duration: Annotated[str, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    end_date: Annotated[datetime.datetime, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    grid: str = "O1280",
    output_dir: ResolvedDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR / "O1280",
) -> None:
    """
    Download ECMWF operational forecast (HRES) data from MARS.

    Downloads high-resolution (~9km) ECMWF operational forecast data in GRIB format
    (one MARS request per variable), by default on the native O1280 octahedral
    Gaussian grid. Requires ECMWF API credentials in `~/.ecmwfapirc`.

    Time range
    ----------
     * ``--start-date`` is the first day of data to download.
     * ``--end-date`` is **exclusive**: data up to (but not including) that date is downloaded.
     * Instead of ``--end-date``, you can pass ``--duration`` as an ISO 8601 string. The exclusive end date is then computed as ``start_date + duration``.

    Examples
    ---------
    The following command is the same:
    ```
    meteo download mars --variable msl --start-date 20240101 --end-date 20240201   # all of January 2024
    meteo download mars --variable msl --start-date 20240101 --duration P1M        # same: 2024-01-01 to 2024-01-31
    ```
    and creates the output file:
     * ``{output_dir}/grib/2024/o1280_20240101_P31D_msl.grib``

    Parameters
    ----------
    start_date : datetime.datetime
        Start date in YYYYMMDD format
    variable : str
        ECMWF variable code. Supported variables include: 'msl' (mean sea level
        pressure), 'u10'/'v10' (10m wind components), 't2m' (2m temperature),
        'sh2' (2m specific humidity), 'ssrd'/'strd' (surface radiation), 'tp'
        (total precipitation).
    end_date : datetime.datetime
        Last day of data to download, **exclusive** (YYYYMMDD format).
        Cannot be called if ``duration`` is provided.
    duration : str
        ISO 8601 string for period to download (e.g., `PnD`, `PnW`, `PnM`, `PnY` and combinations like `P1M15D`).
        Cannot be called if ``end_date`` is provided.
    grid : str
        MARS grid keyword, by default ``O1280`` (native HRES octahedral Gaussian grid).
        O1280 output must be regridded (``meteo convert regrid``) before conversion to sflux.
    output_dir : Path, default: system-specific
        Output directory for downloaded files. Defaults to a platform-specific location.
    """
    from meteo._ecmwf import download_mars
    from meteo._utils import resolve_end_date

    download_mars(
        variable=variable,
        start_date=start_date,
        end_date=resolve_end_date(start_date, end_date, duration),
        output_dir=output_dir,
        grid=grid,
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


def cli_convert_regrid(
    *,
    input_file: Annotated[Path, Parameter(validator=validators.Path(exists=True, file_okay=True, dir_okay=False))],
    output_file: pathlib.Path,
    out_grid: str | None = None,
    in_grid: str | None = None,
    mir_cache_path: ResolvedDirectory = _DEFAULT_CACHE_DIR,
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
) -> None:
    """
    Regrid a GRIB/NetCDF file with MIR (via earthkit-geo).

    The input grid is inferred directly from the file (earthkit grid metadata,
    or uniform lat/lon coordinates), so native downloads can be regridded without
    any extra context:

    - O1280 MARS files default to ``F1280`` output.
    - N320 ERA5 files default to ``[0.1 x 0.1]`` output.

    Examples
    ---------
    ```
    meteo convert regrid --input-file o1280_20240101_P31D_msl.grib --output-file f1280_20240101_P31D_msl.nc
    meteo convert regrid --input-file era5_n320_20250101_P31D_instant.grib --output-file era5_20250101_P31D_instant.nc --out-grid 0.25
    ```

    Parameters
    ----------
    input_file:
        Path to the input file (GRIB or NetCDF).
    output_file:
        Path of the regridded dataset (``.nc`` or ``.zarr``).
    out_grid:
        MIR target grid: a Gaussian grid name (``F1280``, ``N320``, ...) or a regular
        lat/lon increment (``0.25`` or ``0.25x0.5``). Defaults to the full Gaussian
        grid matching the input resolution (e.g. O1280 -> F1280, N320 -> F320).
    in_grid:
        MIR source grid. Only needed when the input grid cannot be inferred from the
        file (e.g. Gaussian grids saved to plain NetCDF without metadata).
    mir_cache_path : Path, default: system cache
        Cache directory for MIR (Meteorological Interpolation and Regridding)
        operations to speed up repeated conversions.
    overwrite:
        Whether to overwrite the output file if it already exists.

    Notes
    -----
    With a *bare* octahedral input grid spec (``--in-grid O1280``), MIR shifts the output
    by 180° in longitude; the data is rolled back into place after interpolation.
    When the grid is inferred from the file (the default), the full grid spec including
    the area is passed to MIR and no shift occurs.
    """
    from meteo._convert import regrid
    from meteo._utils import parse_grid
    from meteo._utils import write_file

    ds_out = regrid(
        input_path=input_file,
        out_grid=parse_grid(out_grid) if out_grid else None,
        in_grid=parse_grid(in_grid) if in_grid else None,
        mir_cache_path=mir_cache_path,
    )
    write_file(
        ds=ds_out,
        output_file=output_file,
        overwrite=overwrite
    )


def cli_convert_mars_to_sflux(
    *,
    group: L_sflux_groups,
    start_date: datetime.datetime,
    duration: Annotated[str, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    end_date: Annotated[datetime.datetime, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    input_dir: ResolvedExistingDirectory = _DEFAULT_ECMWF_OPERATIONAL_DIR,
    output_dir: Path = _DEFAULT_ECMWF_OPERATIONAL_DIR / "sflux",
    out_grid: str | None = None,
    mir_cache_path: ResolvedDirectory = _DEFAULT_CACHE_DIR,
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
):
    """
    Convert MARS forecast files to SCHISM sflux files.

    By specifying the variable `group` (air, rad, prc) and the period (`start_date` with `end_date` or `duration`),
    the per-variable files needed for the group are discovered recursively under ``input_dir`` by their
    ``{grid}_{start}_{duration}_{variable}`` naming convention (as produced by ``meteo download mars``, optionally
    regridded with ``meteo convert regrid``), and merged into a single NetCDF. The grid is inferred from the files
    themselves: native O1280 reduced Gaussian files are regridded on the fly with MIR to ``--out-grid`` (default:
    the matching regular Gaussian grid, F1280), while files already on a structured latitude/longitude grid are
    used as-is (regridded only when ``--out-grid`` is given).

    The program returns an error if any of the required files is missing.

    Parameters
    ----------
    group : str
        Variable group to convert: 'air', 'rad', or 'prc'.
    start_date : datetime.datetime
        Start date of the downloaded data in YYYYMMDD format.
    end_date : datetime.datetime
        Last day of the downloaded data, **exclusive** (YYYYMMDD format).
        Cannot be called if ``duration`` is provided.
    duration : str
        ISO 8601 string for the downloaded period (e.g. `P1M`).
        Cannot be called if ``end_date`` is provided.
    input_dir : Path
        Directory scanned (recursively) for the ``{grid}_{start}_{duration}_{variable}.{grib,nc}`` files.
    output_dir : Path
        Output directory for sflux NetCDF files.
    out_grid : str
        Rectilinear output grid for on-the-fly regridding: a regular Gaussian grid (``F1280``) or a
        regular lat/lon increment (``0.25``, ``0.25x0.5``). Defaults to the regular Gaussian grid
        matching the input resolution (``F1280`` for ``O1280``); structured inputs are used as-is.
    mir_cache_path : Path, default: system cache
        Cache directory for MIR interpolation weights.
    overwrite : bool
        Whether to overwrite existing output files.
    """
    from meteo._sflux import mars_to_sflux
    from meteo._utils import rectilinear_grid
    from meteo._utils import resolve_end_date

    mars_to_sflux(
        group=group,
        start_date=start_date,
        end_date=resolve_end_date(start_date, end_date, duration),
        input_dir=input_dir,
        output_dir=output_dir,
        out_grid=rectilinear_grid(out_grid) if out_grid else None,
        mir_cache_path=mir_cache_path,
        overwrite=overwrite,
    )


def cli_download_era5(
    *,
    start_date: datetime.datetime,
    duration: Annotated[str, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    end_date: Annotated[datetime.datetime, Parameter(group=_TIME_RANGE_VALIDATOR)] | None = None,
    variable: Annotated[L_ERA5_Variables, Parameter(show_choices=True)] = None,
    grid: str = "n320",
    output_dir: ResolvedDirectory = _DEFAULT_ERA5_DIR,
) -> None:
    """
    Download ERA5 from the Copernicus CDS using
    [`earthkit-data`](https://earthkit-data.readthedocs.io/)

    The ``--grid`` value selects the target grid: ``n320`` (the default) retrieves the native
    archived grid from `reanalysis-era5-complete` (the only Gaussian grid served by CDS),
    while a resolution in degrees interpolates to regular lat/lon from
    `reanalysis-era5-single-levels`:

    | `--grid`         | CDS dataset                     | Grid                                   |
    |------------------|---------------------------------|----------------------------------------|
    | `n320` (default) | `reanalysis-era5-complete`      | N320 reduced Gaussian (~31 km, 542080 points) |
    | `0.25`           | `reanalysis-era5-single-levels` | 0.25° regular lat/lon (1440 × 721)     |

    `n320` requests go to the MARS tape archive and queue longer than regular lat/lon ones.
    The N320 output is a reduced Gaussian grid, so it must be regridded before conversion to
    sflux, e.g.: ``meteo convert regrid --input-file era5_n320_...nc --output-file ...nc``
    (the input grid is inferred from the file; the default target is F320).

    The ERA5 request downloads by default variables for hydrodynamic baroclinic simulations,
    divided in two groups of **different `stepType`** values:

    | `stepType`  | Variables                         | Time dimension                  |
    |------------|-----------------------------------|----------------------------------|
    | `instant`  | `u10`, `v10`, `d2m`, `t2m`, `msl` | Hourly (`time` of length 720) |
    | `avg`      | `avg_tprate`, `avg_sdswrf`, `avg_sdlwrf` | 12-hour forecast steps from twice-daily reference times (61 `time` × 12 `step`) |

    The request is thus split into two sub-requests to avoid having a unique dataset with mixed `stepType`, inducing errors when opening the full dataset with xarray.

    Time range
    ----------
     * ERA5 is available from 1940-01-01 until ~5 days before today (ERA5T preliminary data, near-real-time latency).
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
     * ``{output_dir}/era5_n320_20250101_P31D_avg.nc``
     * ``{output_dir}/era5_n320_20250101_P31D_instant.nc``

    With ``--grid 0.25`` the files carry the resolution tag instead
    (e.g. ``{output_dir}/era5_0.25x0.25_20250101_P31D_instant.nc``).
    For the native `avg` group, the 06/18 UTC forecasts (steps 1-12) are requested starting one day
    before ``--start-date`` so the first hours of the period are covered.

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
    grid : str
        ``n320`` (the default — native archived grid from `reanalysis-era5-complete`, the only
        Gaussian grid served) or a resolution in degrees (e.g. ``0.25``) for regular lat/lon
        output from `reanalysis-era5-single-levels`.
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
        grid=grid,
    )


def cli_convert_era5_to_sflux(
    *,
    file: Annotated[Path, Parameter(validator=validators.Path(exists=True, file_okay=True, dir_okay=False))],
    group: L_sflux_groups,
    out_grid: str = "0.1",
    output_dir: Path = _DEFAULT_ERA5_DIR / "sflux",
    mir_cache_path: ResolvedDirectory = _DEFAULT_CACHE_DIR,
    overwrite: Annotated[bool, Parameter(negative=False)] = False,
):
    """
    Convert ERA5 GRIB/NetCDF files to SCHISM sflux format.

    ERA5 GRIB files mix instant and averaged variables with incompatible time axes, so they must be opened separately by stepType before conversion.
    The input grid is inferred from the file (native N320 reduced Gaussian, or any regular lat/lon grid) and the data
    is regridded with MIR onto the rectilinear ``--grid`` (default 0.1°) before conversion. Regridding is skipped when
    the input is already on the target grid.

    Note: This implementation assumes global ERA5 input data intended for interpolation onto global models. Longitude is padded by default (cyclic wrap-around) to ensure periodic continuity across the -180°/180° boundary.

    Examples
    ---------
    ```
    meteo convert era5-to-sflux --file era5_n320_20250101_P31D_instant.nc --group air                  # 0.1° (default)
    meteo convert era5-to-sflux --file era5_n320_20250101_P31D_avg.nc --group rad --out-grid 0.25x0.5
    ```
    creates ``{output_dir}/sflux_era5_0.1x0.1_20250101_P31D_instant_air.nc`` and
    ``{output_dir}/sflux_era5_0.25x0.5_20250101_P31D_avg_rad.nc``.

    Parameters
    ----------
    file: Path
        Path to the input GRIB/NetCDF file containing ERA5 data, for either the `air`, `rad`, or `prc` group.
        * For `air` variables (`u10`, `v10`, `d2m`, `t2m`, `msl`), the file should contain hourly data with `stepType=instant`.
        * For `rad` variables (`avg_sdswrf`, `avg_sdlwrf`), the file should contain 12-hourly averaged data with `stepType=avg`.
        * For `prc` variable (`avg_tprate`), the file should contain 12-hourly averaged data with `stepType=avg`.
    group: str
        Variable group to convert. Must be one of 'air', 'rad', or 'prc'.
    out_grid: str
        Rectilinear output grid (1-D latitude/longitude): a regular lat/lon increment in degrees,
        ``0.1`` (default), ``0.25``, or ``dlon x dlat`` like ``0.25x0.5``; or a regular Gaussian grid (``F320``).
        Reduced/octahedral grids (``N320``, ``O1280``) are rejected.
    output_dir: Path
        Output directory. Files are written as `sflux_era5_{grid}_{start}_{duration}_{kind}_{group}.nc`.
        Defaults to `_DEFAULT_ERA5_DIR/sflux` which is a platform-specific location.
    mir_cache_path : Path, default: system cache
        Cache directory for MIR interpolation weights.
    overwrite: bool
        Whether to overwrite the output file if it already exists.
    """

    from meteo._sflux import era5_to_sflux
    from meteo._utils import rectilinear_grid

    era5_to_sflux(
        file=file,
        group=group,
        output_dir=output_dir,
        overwrite=overwrite,
        grid=rectilinear_grid(out_grid),
        mir_cache_path=mir_cache_path,
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
    )
