import logging
import os
import pathlib
from typing import Union

logger = logging.getLogger(__name__)


def o1280_to_f1280(
    o1280_path: pathlib.Path,
    f1280_path: pathlib.Path,
    mir_cache_path: pathlib.Path | None = None,
    metview_tmp_path : pathlib.Path | None = None,
    mars_maxforks : int | None = None,
    ) -> None:
    # Set env variables before importing metview
    if mir_cache_path is not None:
        mir_cache_path.mkdir(parents=True, exist_ok=True)
        os.environ["MIR_CACHE_PATH"] = str(mir_cache_path)
    if metview_tmp_path is not None:
        metview_tmp_path.mkdir(parents=True, exist_ok=True)
        os.environ["METVIEW_TMPDIR"] = str(metview_tmp_path)
    if mars_maxforks is not None:
        os.environ["MARS_MAXFORKS"] = str(mars_maxforks)

    # Now import metview
    import metview as mv

    o1280_path.parent.mkdir(parents=True, exist_ok=True)
    f1280_path.parent.mkdir(parents=True, exist_ok=True)

    fgs = mv.read(source=str(o1280_path), grid="F1280")
    mv.write(str(f1280_path), fgs)


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
    from ._utils import detect_name
    from ._utils import detect_pad_width
    from ._utils import normalize_longitude
    from ._utils import pad_lon
    from ._utils import pad_lat
    from ._utils import write_file

    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output file exists: {output_file}. Use --overwrite.")

    if method_longitude != "auto":
        if not isinstance(method_longitude, int) or method_longitude <= 0:
            raise ValueError("pad_width must be 'auto' or a positive integer.")

    ds = xr.open_dataset(input_file)
    if pad_longitude:
        # convert to 180 convention
        lon_name = detect_name(ds, "longitude")
        ds_norm = normalize_longitude(ds, lon_name, to_360 = False)
        if method_longitude == "auto":
            pad_width = detect_pad_width(ds_norm, lon_name)
            logger.info(f"LON: auto detected pad_width: {pad_width}")
        elif isinstance(method_longitude, int):
            pad_width = method_longitude
        else:
            raise ValueError(f"Invalid pad_width={pad_width!r}. Must be 'auto' or int.")
        ds = pad_lon(ds_norm, pad_width, lon_name)

    if pad_latitude:
        lat_name = detect_name(ds, "latitude")
        ds = pad_lat(
            ds,
            lat_name = lat_name,
            method = method_latitude,
            side = side
        )

    write_file(ds, output_file, overwrite)
