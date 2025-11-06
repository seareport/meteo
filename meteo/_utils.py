import xarray as xr

from ._literals import L_ECMWF_Variables
from ._literals import L_Grids
from ._literals import L_Months


def get_grib_path(variable: L_ECMWF_Variables, year: int, month: L_Months, grid: L_Grids) -> str:
    # XXX: If this path structure changes, update the docstring examples in:
    #      - cli_download_o1280() in _cli.py
    #      - cli_convert_o1280_to_f1280() in _cli.py
    path = f"grib/{year}/{grid[0].lower()}.{year}.{month:02d}.{variable}.grib"
    return path


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
