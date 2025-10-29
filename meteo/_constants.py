from typing import get_args

from ._literals import L_ECMWF_Variables


SUPPORTED_ECMWF_VARIABLES: tuple[L_ECMWF_Variables] = get_args(L_ECMWF_Variables)

ECMWF_VARIABLE_CODES = {
    #(code, is_accumulated)
    "msl": (151, False),
    "u10": (165, False),
    "v10": (166, False),
    "t2m": (167, False),
    "sh2": (174096, False),
    "ssrd": (169, True),
    "strd": (175, True),
    #"tprate": (260048, False),
    "tp": (228, True),
}

for key in ECMWF_VARIABLE_CODES:
    assert key in SUPPORTED_ECMWF_VARIABLES, f"{key} not in: {SUPPORTED_ECMWF_VARIABLES}"

