import logging
import os
import pathlib
from typing import Union

import earthkit.geo as ekg
import numpy as np
import xarray as xr

from ._utils import default_out_grid
from ._utils import detect_name
from ._utils import infer_grid
from ._utils import is_octahedral
from ._utils import normalize_var_names
from ._utils import open_meteo_file
from ._utils import RECTILINEAR_GRID_TYPES

logger = logging.getLogger(__name__)


def regrid(
        input_path: pathlib.Path,
        out_grid: dict | None = None,
        in_grid: dict | None = None,
        mir_cache_path: pathlib.Path | None = None,
    ) -> xr.Dataset:
    """Regrid a GRIB/NetCDF file with MIR (via earthkit-geo).

    The input grid is inferred from the file itself (earthkit grid metadata or
    uniform lat/lon coordinates) unless ``in_grid`` is given explicitly.
    """
    if mir_cache_path is not None:
        os.environ.setdefault("MIR_CACHE_PATH", str(mir_cache_path))
    ds = open_meteo_file(input_path)
    user_in_grid = in_grid
    if in_grid is None:
        in_grid = infer_grid(ds)
        if in_grid is None:
            raise ValueError(
                f"Could not infer the input grid of {input_path}. "
                "Pass it explicitly with --in-grid (e.g. --in-grid F1280)."
            )
    if out_grid is None:
        out_grid = default_out_grid(in_grid)

    from eckit.geo import Grid

    if Grid(out_grid).type in RECTILINEAR_GRID_TYPES:
        # earthkit-geo 1.2.0 xarray regrid crashes ('_eckit_geo.Grid' has no 'copy');
        # regrid_dataset re-infers the grid itself, adding the area for structured inputs
        return regrid_dataset(ds, out_grid=out_grid, in_grid=user_in_grid)

    logger.info("regridding %s -> %s", in_grid, out_grid)

    ds_out = ekg.regrid(ds, in_grid=in_grid, out_grid=out_grid)

    # drop size-1 GRIB dims: number (ensemble member), surface (3D level)
    singleton_dims = [d for d in ("number", "surface") if ds_out.sizes.get(d) == 1]
    ds_out = ds_out.squeeze(singleton_dims, drop=True)

    return normalize_var_names(ds_out)


def _structured_grid_spec(ds: xr.Dataset, lat_name: str, lon_name: str) -> dict | None:
    # expects lat sorted N->S and lon ascending (MIR scanning order)
    lat = ds[lat_name].values
    lon = ds[lon_name].values
    dx = np.unique(np.round(np.diff(lon), 6))
    dy = np.unique(np.round(np.abs(np.diff(lat)), 6))
    if dx.size != 1 or dy.size != 1:
        return None
    return {
        "grid": [float(dx[0]), float(dy[0])],
        "area": [float(lat[0]), float(lon[0]), float(lat[-1]), float(lon[-1])],
    }


def _is_on_grid(ds: xr.Dataset, lat_name: str, lon_name: str, target) -> bool:
    lat = np.sort(ds[lat_name].values)[::-1]
    lon = np.sort(ds[lon_name].values % 360)
    t_lat = np.asarray(target.distinct_latitudes())
    t_lon = np.sort(np.asarray(target.distinct_longitudes()) % 360)
    return (
        lat.shape == t_lat.shape
        and lon.shape == t_lon.shape
        and np.allclose(lat, t_lat)
        and np.allclose(lon, t_lon)
    )


def regrid_dataset(
    ds: xr.Dataset,
    out_grid: dict,
    in_grid: dict | None = None,
    interpolation: str = "linear",
) -> xr.Dataset:
    # Lazy (dask, one task per 2-D field) MIR regridding onto a rectilinear grid.
    # Output dims are always (..., latitude, longitude), latitude N->S, float32.
    from earthkit.geo.grids.array import regrid as regrid_array
    from eckit.geo import Grid

    lat_name = detect_name(ds, "latitude")
    lon_name = detect_name(ds, "longitude")
    target = Grid(out_grid)

    structured = lat_name in ds.dims and lon_name in ds.dims
    if structured:
        if _is_on_grid(ds, lat_name, lon_name, target):
            logger.info("input already on %s, skipping regrid", out_grid)
            return ds
        ds = ds.sortby(lon_name).sortby(lat_name, ascending=False)
        in_dims = [lat_name, lon_name]
        if in_grid is None:
            # explicit area: a bare increment spec makes MIR assume lon starting at 0
            in_grid = _structured_grid_spec(ds, lat_name, lon_name) or infer_grid(ds)
    else:
        in_dims = list(ds[lat_name].dims)
        if in_grid is None:
            in_grid = infer_grid(ds)
    if in_grid is None:
        raise ValueError("Could not infer the input grid; regrid it first with `meteo convert regrid --in-grid ...`.")
    logger.info("regridding %s -> %s", in_grid, out_grid)

    shape = tuple(target.shape)

    def _regrid_field(values: np.ndarray) -> np.ndarray:
        if np.isnan(values).all():  # missing GRIB message (e.g. init/step combos)
            return np.full(shape, np.nan, dtype=np.float32)
        out, _ = regrid_array(
            np.ascontiguousarray(values, dtype=np.float64).ravel(),
            in_grid,
            out_grid,
            interpolation=interpolation,
        )
        return np.asarray(out, dtype=np.float32).reshape(shape)

    # build the MIR weights once, before dask threads all race to create them
    _regrid_field(np.zeros([ds.sizes[d] for d in in_dims]))

    geo_vars = [v for v in ds.data_vars if set(in_dims) <= set(ds[v].dims)]
    src = ds[geo_vars]
    src = src.drop_vars([c for c in src.coords if set(src[c].dims) & set(in_dims)])
    src = src.chunk({d: (-1 if d in in_dims else 1) for d in src.dims})

    out = xr.apply_ufunc(
        _regrid_field,
        src,
        input_core_dims=[in_dims],
        output_core_dims=[["_lat", "_lon"]],
        vectorize=True,
        dask="parallelized",
        dask_gufunc_kwargs={"output_sizes": {"_lat": shape[0], "_lon": shape[1]}},
        output_dtypes=[np.float32],
        keep_attrs=True,
    )
    out = out.rename({"_lat": "latitude", "_lon": "longitude"}).assign_coords(
        latitude=(
            "latitude",
            np.asarray(target.distinct_latitudes()),
            {"standard_name": "latitude", "units": "degrees_north"},
        ),
        longitude=(
            "longitude",
            np.asarray(target.distinct_longitudes()),
            {"standard_name": "longitude", "units": "degrees_east"},
        ),
    )
    out.attrs = dict(ds.attrs)
    return out


def convert_normalize_longitude(
    input_file: pathlib.Path,
    output_file: pathlib.Path,
    longitude_convention: str,
    overwrite: bool,
    )-> None:
    import xarray as xr
    from ._utils import detect_name
    from ._utils import normalize_longitude
    from ._utils import write_file


    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output file exists: {output_file}. Use --overwrite.")

    ds = xr.open_dataset(input_file)
    lon_name = detect_name(ds, "longitude")
    ds_norm = normalize_longitude(ds, lon_name, to_360 = longitude_convention == "360")
    write_file(ds_norm, output_file, overwrite)


def convert_pad(
    input_file: pathlib.Path,
    output_file: pathlib.Path,
    pad_longitude: bool,
    pad_latitude: bool,
    method_longitude: Union[str, int],
    method_latitude: str,
    side: str,
    overwrite: bool,
    )->None:
    import xarray as xr
    from ._utils import auto_pad_lon
    from ._utils import auto_pad_lat
    from ._utils import write_file

    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output file exists: {output_file}. Use --overwrite.")

    if method_longitude != "auto":
        if not isinstance(method_longitude, int) or method_longitude <= 0:
            raise ValueError("pad_width must be 'auto' or a positive integer.")

    ds = xr.open_dataset(input_file, decode_cf=False)
    if pad_longitude:
        ds = auto_pad_lon(ds, method_longitude)

    if pad_latitude:
        ds = auto_pad_lat(
            ds,
            method_latitude = method_latitude,
            side = side
        )

    write_file(ds, output_file, overwrite)
