from typing import get_args

from ._literals import L_ECMWF_Variables
from ._literals import L_ERA5_Variables

# ECMWF
SUPPORTED_ECMWF_VARIABLES: tuple[L_ECMWF_Variables] = get_args(L_ECMWF_Variables)
SUPPORTED_ERA5_VARIABLES: tuple[L_ERA5_Variables] = get_args(L_ERA5_Variables)

ECMWF_VARIABLE_CODES = {
    # info on parameter codes: https://codes.ecmwf.int/grib/param-db/
    # (code, is_accumulated)
    "msl": (151, False),
    "u10": (165, False),
    "v10": (166, False),
    "t2m": (167, False),
    "sh2": (174096, False),
    "ssrd": (169, True),
    "strd": (175, True),
    # "tprate": (260048, False),
    "tp": (228, True),
    "2d": (168, False),
}

for key in ECMWF_VARIABLE_CODES:
    assert key in SUPPORTED_ECMWF_VARIABLES, f"{key} not in: {SUPPORTED_ECMWF_VARIABLES}"

ERA5_SFLUX_MAPPING = {
    "air": {
        "msl": "prmsl",
        "u10": "uwind",
        "v10": "vwind",
        "sh2": "spfh",
        "t2m": "stmp",
    },
    "rad": {
        "avg_sdswrf": "dswrf",
        "avg_sdlwrf": "dlwrf",
    },
    "prc": {
        "avg_tprate": "prate",
    },
}

ERA5_REQUIRED_VARS = {
    "air": {"u10", "v10", "msl", "t2m", "d2m"}, # not sh2 because it is computed from t2m, d2m and msl
    "rad": {"avg_sdswrf", "avg_sdlwrf"},
    "prc": {"avg_tprate"},
}

F1280_SFLUX_MAPPING = {
    "air": {
        "msl": "prmsl",
        "sh2": "spfh",
        "t2m": "stmp",
        "u10": "uwind",
        "v10": "vwind",
    },
    "rad": {
        "ssrd": "dswrf",
        "strd": "dlwrf",
    },
    "prc": {
        "tp": "prate",
    },
}

ATTRIBUTES = {
    "time": {
        "long_name": "Time",
        "standard_name": "time",
        # "axis": "T",  # Optional but helpful
    },
    "lon": {
        "long_name": "Longitude",
        "standard_name": "longitude",
        "units": "degrees_east",
    },
    "lat": {
        "long_name": "Latitude",
        "standard_name": "latitude",
        "units": "degrees_north",
    },
    "uwind": {
        "long_name": "Surface Eastward Air Velocity (10m AGL)",
        "standard_name": "eastward_wind",
        "units": "m/s",
    },
    "vwind": {
        "long_name": "Surface Northward Air Velocity (10m AGL)",
        "standard_name": "northward_wind",
        "units": "m/s",
    },
    "prmsl": {
        "long_name": "Pressure reduced to MSL",
        "standard_name": "air_pressure_at_sea_level",
        "units": "Pa",
    },
    "stmp": {
        "long_name": "Surface Air Temperature (2m AGL)",
        "standard_name": "air_temperature",
        "units": "K",
    },
    "spfh": {
        "long_name": "Surface Specific Humidity (2m AGL)",
        "standard_name": "specific_humidity",
        "units": "1",
    },
    "prate": {
        "long_name": "Surface Precipitation Rate",
        "standard_name": "precipitation_flux",
        "units": "kg/m^2/s",
    },
    "dlwrf": {
        "long_name": "Downward Long Wave Radiation Flux",
        "standard_name": "surface_downwelling_longwave_flux_in_air",
        "units": "W/m^2",
    },
    "dswrf": {
        "long_name": "Downward Short Wave Radiation Flux",
        "standard_name": "surface_downwelling_shortwave_flux_in_air",
        "units": "W/m^2",
    },
}

# HYCOM
HYCOM_MAX_DEPTH_INDEX = 39
POTENTIAL_TEMP_CORRECTION = 1.00024
SUB_SAMPLE = 1
