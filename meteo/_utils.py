import datetime
import logging
import pathlib

import isoduration
import xarray as xr
from dateutil.relativedelta import relativedelta
from isoduration.types import DateDuration
from isoduration.types import Duration
from isoduration.types import TimeDuration

from ._literals import L_ECMWF_Variables

logger = logging.getLogger(__name__)

CANDIDATES_LON = ["x", "lon", "longitude", "xlon", "nav_lon", "glamt", "glamf", "lon_rho"]
CANDIDATES_LAT = ["y", "lat", "latitude", "ylat", "nav_lat", "gphit", "gphif", "lat_rho"]
GRIB_SUFFIXES = {".grib", ".grb", ".grib2", ".grb2"}
RECTILINEAR_GRID_TYPES = ("regular_ll", "regular_gg")

def get_grib_name(variable: L_ECMWF_Variables, start: datetime.datetime, end: datetime.datetime, grid: str) -> str:
    # XXX: If this naming changes, update the docstring examples in:
    #      - cli_download_mars() in _cli.py
    return f"grib/{start.year}/{grid.lower()}_{start:%Y%m%d}_{compute_duration_tag(start, end)}_{variable}.grib"


# https://gis.stackexchange.com/questions/201789/verifying-formula-that-will-convert-longitude-0-360-to-180-to-180
# long1 is the longitude varying from -180 to 180 or 180W-180E
# long3 is the longitude variable from 0 to 360 (all positive)
def lon1_to_lon3(lon1):
    return lon1 % 360


def lon3_to_lon1(lon3):
    return ((lon3 + 180) % 360) - 180


def normalize_longitude(ds: xr.Dataset, lon_name: str, to_360: bool = True) -> xr.Dataset:
    normalized = ds.copy()
    if to_360:
        normalized[lon_name] = lon1_to_lon3(normalized[lon_name])
    else:
        normalized[lon_name] = lon3_to_lon1(normalized[lon_name])
    normalized = normalized.sortby([lon_name])
    return normalized


def normalize_latitude(ds: xr.Dataset, lat_name: str) -> xr.Dataset:  # pylint: disable=invalid-name
    normalized = ds.sortby([lat_name])
    return normalized


def normalize_ds(ds: xr.Dataset, to_360: bool = True) -> xr.Dataset:
    lon_name = detect_name(ds, var= "longitude")
    lat_name = detect_name(ds, var= "latitude")
    normalized = normalize_longitude(
        normalize_latitude(ds, lat_name = lat_name),
        lon_name,
        to_360)
    return normalized


def detect_name_in_ds(ds: xr.Dataset, candidates: list[str]):
    """
    Detect coordinate name using:
    1) CF conventions
    2) Name-based lookup in coords
    3) Name-based lookup in variables
    """
    import cf_xarray
    cand_set = {c.lower() for c in candidates}
    try:
        if "longitude" in cand_set and "longitude" in ds.cf.coordinates:
            return ds.cf.coordinates["longitude"][0]

        if "latitude" in cand_set and "latitude" in ds.cf.coordinates:
            return ds.cf.coordinates["latitude"][0]

    except Exception:
        pass

    for name in ds.coords:
        if name.lower() in candidates:
            return name

    for name in ds.variables:
        if name.lower() in candidates:
            return name

    raise ValueError(f"Could not auto-detect coord name in {candidates}")


def detect_name(ds: xr.Dataset, var = "longitude") -> str:
    if var == "longitude":
        return detect_name_in_ds(ds, CANDIDATES_LON)
    elif var == "latitude":
        return detect_name_in_ds(ds, CANDIDATES_LAT)
    else:
        raise ValueError(f"No candidate associated with {var}")


def detect_pad_width(ds: xr.Dataset, lon_name: str) -> int:
    import numpy as np
    lon = np.sort(ds[lon_name].values)

    if ds[lon_name].ndim != 1:
        raise ValueError(f"Longitude {lon_name} must be 1D for padding.")

    left = lon[0]
    right = lon[-1]
    diffs = np.diff(lon)
    left_step = diffs[0]
    left_pad = int(np.ceil(abs(-180 - left)/left_step))
    right_step = diffs[-1]
    right_pad = int(np.ceil(abs(180 - right)/right_step))

    pad_width = np.max([left_pad, right_pad])

    if pad_width <= 0 or pad_width >= len(lon):
        raise ValueError(f"Invalid auto-detected pad width: {pad_width}")

    return pad_width


def pad_lon(ds: xr.Dataset, pad_width: int, lon_name: str = "longitude") -> xr.Dataset:
    # Pad the Dataset and Normalize longitude values of PAD.
    # We use `wrap` mode in order to handle the Antimeridian
    # Nevertheless it is necessary to "normalize" the longitudes due to the following issue.
    # After padding the longitude values are like this:
    #     179.7 179.9 -179.9 -177.7 .... 177.7 177.9 -177.9 -177.7
    # This causes a problem if we convert to a pandas dataframe and then back to xarray:
    #     df = ds.elevation.to_dataframe()
    #     final = df.to_xarray()
    # The `.to_xarray()` call reorders the index and messes things up. By normalizing
    # the longitude values, i.e. by converting them to:
    #     -180.3 -180.1 -179.9 -177.7 ... 177.7 177.9 180.1 180.3
    # then no reordering happens and we can use normal .isel() to trim the adjusted dataset
    import numpy as np
    padded = ds.pad({lon_name: pad_width}, mode="wrap", keep_attrs=True)
    lon = padded[lon_name].values
    padded = padded.assign_coords({
        lon_name: np.concatenate((
            -180 - (180 - lon[:pad_width]),
            lon[pad_width:-pad_width],
            lon[-pad_width:] % 360,
        )),
    })
    return padded

def auto_pad_lon(ds: xr.Dataset, method_longitude: str | int) -> xr.Dataset:
    """
    Pad a dataset along longitude, first normalizing coords to [-180, 180].

    This is the main entry point for longitude padding. It:
      1. Detects the longitude coordinate name in the dataset.
      2. Normalizes longitudes to the [-180, 180] range (required by
         ``pad_lon``, which hardcodes 180 in its wrap arithmetic).
      3. Determines the pad width, either automatically from the grid
         resolution or from an explicit integer.
      4. Delegates to ``pad_lon`` for the actual padding and coordinate fix-up.

    Parameters
    ----------
    ds : xr.Dataset
        xarray Dataset to pad.
    method_longitude : str or int
        method to determine pad width. Options:
         - "auto": Detect pad width based on longitude resolution and distance to the poles.
         - int: Use the provided integer as pad width.

    Returns
    -------
    Padded xarray Dataset.
    """
    lon_name = detect_name(ds, "longitude")
    ds_norm = normalize_longitude(ds, lon_name, to_360 = False)
    if method_longitude == "auto":
        pad_width = detect_pad_width(ds_norm, lon_name)
        logger.info(f"LON: auto detected pad_width: {pad_width}")
    elif isinstance(method_longitude, int):
        pad_width = method_longitude
    else:
        raise ValueError(f"Invalid pad_width={pad_width!r}. Must be 'auto' or int.")
    return pad_lon(ds_norm, pad_width, lon_name)


def pad_lat(
    ds: xr.Dataset,
    lat_name: str = "latitude",
    method: str = "fade",
    side: str = "north",
) -> xr.Dataset:
    import numpy as np
    if side not in ("south", "north", "both"):
        raise ValueError(f"side={side!r}, must be one of 'south', 'north', 'both'")

    original_dims = {var: ds[var].dims for var in ds.data_vars}
    lat = ds[lat_name].values
    ascending = lat[-1] > lat[0]  # True: south to north direction

    #   "south" pole lives at index 0 when ascending, index -1 when descending
    #   "north" pole lives at index -1 when ascending, index 0 when descending
    diffs = np.abs(np.diff(lat))
    result = ds

    if side in ("south", "both"):
        if ascending:
            edge_idx = 0
            lat_step = diffs[0]
        else:
            edge_idx = -1
            lat_step = diffs[-1]
        result = _pad_lat_single_side(result, lat_name, lat_step, method, pole=-90.0, edge_idx=edge_idx, ascending=ascending)

    if side in ("north", "both"):
        if ascending:
            edge_idx = -1
            lat_step = diffs[-1]
        else:
            edge_idx = 0
            lat_step = diffs[0]
        result = _pad_lat_single_side(result, lat_name, lat_step, method, pole=90.0, edge_idx=edge_idx, ascending=ascending)

    for var, dims in original_dims.items():
        if result[var].dims != dims:
            result[var] = result[var].transpose(*dims)

    return result


def auto_pad_lat(ds: xr.Dataset, method_latitude: str, side: str) -> xr.Dataset:
    """
    Pad dataset to the poles (+/-90°) based on the detected resolution and on the latitude coordinates direction.

    Parameters
    ----------
    ds : xr.Dataset
        xarray Dataset to pad.
    method_latitude : str
        method to fill the padded latitudes. Options:
         - "fade": Blend boundary row linearly toward nanmedian at the pole.
         - "median": Fill with nanmedian of boundary row.
    side : str
        side to pad. Options:
         - "south": Pad only the south side
         - "north": Pad only the north side
         - "both": Pad both sides
    """
    lat_name = detect_name(ds, "latitude")
    return pad_lat(ds, lat_name, method_latitude, side=side)


def _pad_lat_single_side(
    ds: xr.Dataset,
    lat_name: str,
    lat_step: float,
    method: str,
    pole: float,
    edge_idx: int,
    ascending: bool,
) -> xr.Dataset:
    import numpy as np
    if lat_step <= 0 or np.isnan(lat_step):
        raise ValueError(f"Cannot detect valid latitude spacing from {lat_name}")

    lat_edge = ds[lat_name].values[edge_idx]

    if pole > 0 and lat_edge >= pole:
        return ds
    if pole < 0 and lat_edge <= pole:
        return ds

    n_extra = int(np.ceil(abs(pole - lat_edge) / lat_step))
    new_lats = lat_edge + np.sign(pole - lat_edge) * lat_step * np.arange(1, n_extra + 1)
    new_lats[-1] = pole
    new_lats = np.sort(new_lats) if ascending else np.sort(new_lats)[::-1]

    edge_row = ds.isel({lat_name: edge_idx})
    medians = {var: np.nanmedian(edge_row[var].values) for var in ds.data_vars}

    padded_rows = []

    for lat_i in new_lats:
        if method == "median":
            new_row = xr.Dataset({
                var: xr.full_like(edge_row[var], medians[var])
                for var in ds.data_vars
            })
        elif method == "fade":  # linear fade from edge row to pole
            w = abs(lat_i - lat_edge) / abs(pole - lat_edge)
            new_row = xr.Dataset({
                var: (1 - w) * edge_row[var] + w * medians[var]
                for var in ds.data_vars
            })
        else:
            raise ValueError(f"Unknown method '{method}'. Choose: fade, median")

        new_row = new_row.assign_coords({lat_name: lat_i})
        padded_rows.append(new_row)

    padded_block = xr.concat(padded_rows, dim=lat_name)

    prepend = (edge_idx == 0)
    if prepend:
        return xr.concat([padded_block, ds], dim=lat_name)
    else:
        return xr.concat([ds, padded_block], dim=lat_name)


def write_file(ds: xr.Dataset, output_file: pathlib.Path, overwrite: bool, encoding = None) -> None:
    if not overwrite and output_file.exists():
        raise FileExistsError(f"{output_file} already exists")

    out_suffix = output_file.suffix.lower()
    if out_suffix == ".zarr":
        ds.to_zarr(output_file, mode="w")
    elif out_suffix == ".nc":
        ds.to_netcdf(output_file, encoding=encoding)
    else:
        raise NotImplementedError(f"export for {out_suffix} is not available")


def open_meteo_file(path: pathlib.Path) -> xr.Dataset:
    """Open a GRIB/NetCDF meteo file, normalizing names to cfgrib conventions."""
    path = pathlib.Path(path)
    if path.suffix.lower() in GRIB_SUFFIXES:
        import earthkit.data as ekd
        ds = ekd.from_source("file", str(path)).to_xarray()
    else:
        ds = xr.open_dataset(path)
    ds = normalize_var_names(ds)
    singleton_dims = [d for d in ("number", "surface") if d in ds.dims and ds.sizes[d] == 1]
    if singleton_dims:
        ds = ds.squeeze(singleton_dims, drop=True)
    return ds


def normalize_var_names(ds: xr.Dataset) -> xr.Dataset:
    """Rename ecCodes/earthkit GRIB shortNames to cfgrib-style names and
    ``forecast_reference_time`` to ``time`` (earthkit GRIB engine conventions)."""
    from ._constants import GRIB_SHORTNAME_ALIASES

    rename = {}
    for canonical, shortname in GRIB_SHORTNAME_ALIASES.items():
        if shortname in ds.variables and canonical not in ds.variables:
            rename[shortname] = canonical
    if "forecast_reference_time" in ds.dims and "time" not in ds.dims:
        rename["forecast_reference_time"] = "time"
    return ds.rename(rename) if rename else ds


def infer_grid(ds: xr.Dataset) -> dict | None:
    """Infer the grid spec of a dataset, e.g. ``{"grid": "O1280"}`` or ``{"grid": [0.25, 0.25]}``.

    Uses earthkit metadata when available (GRIB sources and files written by earthkit),
    otherwise falls back to uniform 1D latitude/longitude coordinates.
    Returns None when the grid cannot be described as a MIR grid spec
    (e.g. Gaussian latitudes saved without metadata).
    """
    import numpy as np

    try:
        import earthkit.data  # noqa: F401  (registers the .earthkit xarray accessor)
        spec = ds.earthkit.grid_spec
    except Exception:
        spec = None
    if spec:
        return dict(spec)
    try:
        lon_name = detect_name(ds, "longitude")
        lat_name = detect_name(ds, "latitude")
    except ValueError:
        return None
    lon, lat = ds[lon_name], ds[lat_name]
    if lon.ndim == 1 and lat.ndim == 1:
        dx = np.unique(np.round(np.diff(lon.values), 6))
        dy = np.unique(np.round(np.abs(np.diff(lat.values)), 6))
        if dx.size == 1 and dy.size == 1:
            return {"grid": [float(dx[0]), float(dy[0])]}
    return None


def parse_grid(spec: str) -> dict:
    """Parse a grid spec string into a MIR grid dict.

    Accepted formats: Gaussian grid names (``F1280``, ``N320``, ``O1280``) or
    regular lat/lon increments (``0.25``, ``0.25x0.5``, ``0.25/0.5``).
    """
    s = spec.strip()
    for sep in ("x", "/", ","):
        if sep in s:
            parts = s.split(sep)
            if len(parts) != 2:
                raise ValueError(f"Invalid grid spec: {spec!r}")
            return {"grid": [float(parts[0]), float(parts[1])]}
    try:
        value = float(s)
    except ValueError:
        return {"grid": s.upper()}
    return {"grid": [value, value]}


def rectilinear_grid(spec: str | dict) -> dict:
    from eckit.geo import Grid

    grid = parse_grid(spec) if isinstance(spec, str) else dict(spec)
    kind = Grid(grid).type
    if kind not in RECTILINEAR_GRID_TYPES:
        raise ValueError(
            f"Output grid {spec!r} is {kind}, not rectilinear (1-D latitude/longitude). "
            "Use a regular lat/lon increment (e.g. 0.1, 0.25x0.5) or a regular Gaussian grid (e.g. F320)."
        )
    return grid


def default_out_grid(in_grid: dict) -> dict:
    """Default MIR out_grid: the full (regular) Gaussian grid matching the input resolution."""
    grid = in_grid.get("grid")
    if grid == "N320":
        return {"grid": [0.1,0.1]}
    elif grid == "O1280":
        return {"grid": "F1280"}
    else:
        raise ValueError(f"Cannot derive a default out-grid from in_grid={in_grid}; pass --out-grid explicitly")


def is_octahedral(grid_spec: dict) -> bool:
    grid = grid_spec.get("grid")
    return isinstance(grid, str) and grid.startswith("O")


def grid_slug(grid_spec: dict) -> str:
    grid = grid_spec.get("grid")
    if isinstance(grid, str):
        return grid.lower()
    if isinstance(grid, (list, tuple)) and len(grid) == 2:
        return f"{grid[0]:g}x{grid[1]:g}"
    return "unknown"


def ensure_structured_latlon(ds: xr.Dataset, source: str) -> None:
    lon_name = detect_name(ds, "longitude")
    lat_name = detect_name(ds, "latitude")
    if lat_name not in ds.dims or lon_name not in ds.dims:
        raise ValueError(
            f"{source} is not on a structured latitude/longitude grid (dims: {dict(ds.sizes)}). "
            "Regrid it first, e.g. `meteo convert regrid`."
        )


def compute_end_date(start: datetime.datetime, str_duration: str) -> datetime.date:
    duration = isoduration.parse_duration(str_duration)
    return start + duration


def compute_duration_tag(start: datetime.date, end: datetime.date) -> str:
    delta = end - start
    duration = Duration(
        DateDuration(years=0, months=0, days=delta.days, weeks=0),
        TimeDuration(hours=0, minutes=0, seconds=delta.seconds),
    )
    return isoduration.format_duration(duration)


def inclusive_to_exclusive(date_inclusive: datetime.datetime)-> datetime.datetime:
    return date_inclusive - isoduration.parse_duration("PT1H")


def resolve_end_date(
    start: datetime.datetime,
    end_date: datetime.datetime | None,
    duration: str | None,
) -> datetime.datetime:
    if duration:
        return compute_end_date(start, duration)
    if end_date is None:
        raise ValueError("Provide either --end-date or --duration")
    return end_date
