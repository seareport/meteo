import os
import pathlib
import shutil
from collections.abc import Iterator

import numpy as np
import pytest
import xarray as xr
from e2e_utils import assert_close
from e2e_utils import fetch_reference
from e2e_utils import meteo

from meteo._constants import MARS_SFLUX_MAPPING

e2e = pytest.mark.skipif(
    os.environ.get("METEO_E2E_MARS") != "1",
    reason="end-to-end MARS F1280 pipeline (MARS download, ~8 GB peak disk): set METEO_E2E_MARS=1",
)

START, DURATION = "20200101", "P1D"
AIR_DOWNLOADS = ["msl", "u10", "v10", "t2m", "2d", "sp"]  # sh2 is computed from 2d + sp
AVG_DOWNLOADS = ["ssrd", "strd", "tp"]
SFLUX_VARS = {g: list(m.values()) for g, m in MARS_SFLUX_MAPPING.items()}


@pytest.fixture
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[pathlib.Path]:
    # always removed at the end: keeps peak disk usage to one step type at a time
    base = os.environ.get("METEO_E2E_DIR")
    path = pathlib.Path(base) / "mars" if base else tmp_path_factory.mktemp("mars")
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def download(variables: list[str], mars_dir: pathlib.Path) -> None:
    for var in variables:
        meteo("download", "mars", "--start-date", START, "--duration", DURATION, "--variable", var, "--output-dir", mars_dir)


def convert_and_compare(group: str, mars_dir: pathlib.Path, out_dir: pathlib.Path) -> None:
    try:
        meteo(
            "convert", "mars-to-sflux", "--start-date", START, "--duration", DURATION, "--group", group,
            "--input-dir", mars_dir, "--output-dir", out_dir, "--overwrite",
        )  # fmt: skip
        (out,) = out_dir.glob(f"sflux_*_{group}.nc")
        assert out.name == f"sflux_f1280_{START}_{DURATION}_{group}.nc"
        with xr.open_dataset(out) as generated, xr.open_dataset(fetch_reference(f"sflux_f1280_20200101_P1H_{group}.nc")) as ref:
            assert generated.sizes["time"] == 24
            # the reference holds the first step only (air is labelled 00:00, the others 23:30): match by index
            gen = generated.isel(time=0)
            # drop the polar rows (lat ±90): regrid edge values there are not comparable
            gen, ref = gen.isel(ny_grid=slice(1, -1)), ref.isel(ny_grid=slice(1, -1))
            assert (ref.sizes["ny_grid"], ref.sizes["nx_grid"]) == (2559, 5122)
            np.testing.assert_allclose(gen.lon.values, ref.lon.values, atol=1e-3)
            np.testing.assert_allclose(gen.lat.values, ref.lat.values, atol=1e-6)
            for var in SFLUX_VARS[group]:
                assert_close(var, gen[var].values, ref[var].values)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


@e2e
def test_air(workdir: pathlib.Path) -> None:
    download(AIR_DOWNLOADS, workdir / "o1280")
    convert_and_compare("air", workdir / "o1280", workdir / "sflux")


@e2e
def test_rad_prc(workdir: pathlib.Path) -> None:
    # the avg downloads are shared by rad and prc; the rad output is removed before prc is written
    download(AVG_DOWNLOADS, workdir / "o1280")
    convert_and_compare("rad", workdir / "o1280", workdir / "sflux")
    convert_and_compare("prc", workdir / "o1280", workdir / "sflux")
