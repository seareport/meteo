from ._literals import L_Grids
from ._literals import L_Months
from ._literals import L_ECMWF_Variables


def get_grib_path(variable: L_ECMWF_Variables, year: int, month: L_Months, grid: L_Grids) -> str:
    # XXX: If this path structure changes, update the docstring examples in:
    #      - cli_download_o1280() in _cli.py
    #      - cli_convert_o1280_to_f1280() in _cli.py
    path = f"grib/{year}/{grid[0].lower()}.{year}.{month:02d}.{variable}.grib"
    return path
