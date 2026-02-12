from typing import Literal
from typing import Union

L_Grids = Literal["O1280", "F1280"]
L_Months = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
L_Days = Literal[
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31
]
L_6Hours = Literal[0, 6, 12, 18]
L_ECMWF_Variables = Literal["msl", "u10", "v10", "t2m", "sh2", "ssrd", "strd", "tp", "2d", "sp"]
L_ERA5_Variables = Literal[
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_dewpoint_temperature",
    "2m_temperature",
    "mean_sea_level_pressure",
    "mean_surface_downward_long_wave_radiation_flux",
    "mean_surface_downward_short_wave_radiation_flux",
    "mean_total_precipitation_rate"
]
L_ERA5_Instant_Variables = Literal[
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_dewpoint_temperature",
    "2m_temperature",
    "mean_sea_level_pressure"
]
L_ERA5_Avg_Variables = Literal[
    "mean_surface_downward_long_wave_radiation_flux",
    "mean_surface_downward_short_wave_radiation_flux",
    "mean_total_precipitation_rate"
]

L_sflux_groups = Literal["air", "rad", "prc"]

L_CMEMS_Dataset = Literal[
    "cmems_mod_glo_phy", # Global Ocean Physics Analysis and Forecast
    # "cmems_mod_glo_wav", # Global Ocean Waves Analysis and Forecast
]
L_CMEMS_export_format = Literal["cmems", "hycom"]
Lon_Convention = Literal["180", "360"]
PadMethodLon = Union[Literal["auto"], int]
PadMethodLat = Literal["median", "fade"]
PadSideLat = Literal["north", "south", "both"]
