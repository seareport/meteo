from typing import get_args

from ._literals import L_ECMWF_Variables
from ._literals import L_ERA5_Variables

# ECMWF
SUPPORTED_ECMWF_VARIABLES: tuple[L_ECMWF_Variables] = get_args(L_ECMWF_Variables)
SUPPORTED_ERA5_VARIABLES: tuple[L_ERA5_Variables] = get_args(L_ERA5_Variables)

ECMWF_VARIABLE_CODES = {
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

# CMEMS
CMEMS_TO_HYCOM_MAPPING = {
    "latitude": "ylat",
    "longitude": "xlon",
    "uo": "water_u",
    "vo": "water_v",
    "thetao": "temperature",
    "so": "salinity"
}

# HYCOM
HYCOM_MAX_DEPTH_INDEX = 39
POTENTIAL_TEMP_CORRECTION = 1.00024
SUB_SAMPLE = 1
HYCOM_ENCODING_OFFSET0 = {
    "dtype": "h",
    "_FillValue": -30000,
    "scale_factor": 0.001,
    "add_offset": 0.0,
    "missing_value": -30000,
}

HYCOM_ENCODING_OFFSET20 = {
    "dtype": "h",
    "_FillValue": -30000,
    "scale_factor": 0.001,
    "add_offset": 20.0,
    "missing_value": -30000,
}
HYCOM_VARS = ["surf_el", "water_u", "water_v", "temperature", "salinity"]
HYCOM_ARGS = dict(
    unlimited_dims="time",
    encoding={
        "surf_el": HYCOM_ENCODING_OFFSET0,
        "water_u": HYCOM_ENCODING_OFFSET0,
        "water_v": HYCOM_ENCODING_OFFSET0,
        "temperature": HYCOM_ENCODING_OFFSET20,
        "salinity": HYCOM_ENCODING_OFFSET20,
    },
)
HYCOM_VAR_ATTRS = {
    "surf_el": {
        "_CoordinateAxes": "time lat lon ",
        "long_name": "Water Surface Elevation",
        "standard_name": "sea_surface_elevation",
        "units": "m",
        "NAVO_code": 32,
    },
    "salinity": {
        "_CoordinateAxes": "time depth lat lon ",
        "long_name": "Salinity",
        "standard_name": "sea_water_salinity",
        "units": "psu",
        "NAVO_code": 16,
    },
    "water_u": {
        "_CoordinateAxes": "time depth lat lon ",
        "long_name": "Eastward Water Velocity",
        "standard_name": "eastward_sea_water_velocity",
        "units": "m/s",
        "NAVO_code": 17,
    },
    "water_v": {
        "_CoordinateAxes": "time depth lat lon ",
        "long_name": "Northward Water Velocity",
        "standard_name": "northward_sea_water_velocity",
        "units": "m/s",
        "NAVO_code": 18,
    },
    "temperature": {
        "long_name": "Sea water potential temperature",
        "standard_name": "sea_water_potential_temperature",
        "units": "degC",
    },
}

HYCOM_COORD_ATTRS = {
    "ylat": {
        "long_name": "Latitude",
        "standard_name": "latitude",
        "units": "degrees_north",
        "axis": "Y",
        "NAVO_code": 1,
    },
    "xlon": {
        "long_name": "Longitude",
        "standard_name": "longitude",
        "units": "degrees_east",
        "axis": "X",
    },
    "depth": {
        "long_name": "Depth",
        "standard_name": "depth",
        "units": "m",
        "positive": "down",
        "axis": "Z",
        "NAVO_code": 5,
    },
    "time": {
        "long_name": "Valid Time",
        "time_origin": "2000-01-01 00:00:00",
        "axis": "T",
        "NAVO_code": 13,
    },
}
HYCOM_GLOBAL_ATTRS = {
    "classification_level": "UNCLASSIFIED",
    "distribution_statement": "Approved for public release. Distribution unlimited.",
    "downgrade_date": "not applicable",
    "classification_authority": "not applicable",
    "institution": "Fleet Numerical Meteorology and Oceanography Center",
    "source": "HYCOM archive file",
    "history": "archv2ncdf2d",
    "comment": "p-grid",
    "field_type": "instantaneous",
    "Conventions": "CF-1.6 NAVO_netcdf_v1.1",
}
