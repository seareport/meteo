import hashlib
import os
import pathlib
import urllib.request

import numpy as np
import platformdirs

from meteo.__main__ import main_app

ZENODO_URL = "https://zenodo.org/records/23881590/files"
REFERENCE_MD5 = {
    "sflux_era5_20200101_P1H_avg_prc.nc": "e1c67fa81e18a4d296aa9adde68c958f",
    "sflux_era5_20200101_P1H_avg_rad.nc": "23a64d995015b1fcac4c023cff4344c1",
    "sflux_era5_20200101_P1H_instant_air.nc": "285aab27aee7cebb1fd2a0904c7c1d55",
    "sflux_f1280_20200101_P1H_air.nc": "af5e4bc6eaace58623275b639f18fd3d",
    "sflux_f1280_20200101_P1H_prc.nc": "dd9c6844d2d3ce67d62874b75a06f040",
    "sflux_f1280_20200101_P1H_rad.nc": "b4bc07765f6991b64686306ea96e93d1",
}
RTOL, ATOL = 1e-3, 1e-3


def meteo(*args: object) -> object:
    return main_app([str(a) for a in args], exit_on_error=False, result_action="return_value")


def reference_dir() -> pathlib.Path:
    persistent = os.environ.get("METEO_E2E_DIR")
    base = pathlib.Path(persistent) if persistent else pathlib.Path(platformdirs.user_cache_dir("meteo")) / "e2e"
    return base / "reference"


def md5sum(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def fetch_reference(name: str) -> pathlib.Path:
    path = reference_dir() / name
    if path.exists() and md5sum(path) == REFERENCE_MD5[name]:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    urllib.request.urlretrieve(f"{ZENODO_URL}/{name}?download=1", part)
    if (got := md5sum(part)) != REFERENCE_MD5[name]:
        part.unlink()
        raise RuntimeError(f"{name}: md5 mismatch (got {got}, expected {REFERENCE_MD5[name]})")
    part.rename(path)
    return path


def assert_close(var: str, gen: np.ndarray, ref: np.ndarray) -> None:
    np.testing.assert_array_equal(np.isnan(gen), np.isnan(ref), err_msg=f"{var}: NaN masks differ")
    atol = 0.02 if var == "dswrf" else ATOL
    np.testing.assert_allclose(gen, ref, rtol=RTOL, atol=atol, err_msg=var)
