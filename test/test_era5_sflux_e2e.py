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

from meteo._constants import ERA5_SFLUX_MAPPING

e2e = pytest.mark.skipif(
    os.environ.get("METEO_E2E") != "1",
    reason="end-to-end ERA5 pipeline (CDS download, several GB): set METEO_E2E=1",
)

START, DURATION = "20200101", "P7D"
SOURCES = {"air": "instant", "rad": "avg", "prc": "avg"}
WRONG_SOURCES = {"air": "avg", "rad": "instant", "prc": "instant"}
REFERENCES = {g: f"sflux_era5_20200101_P1H_{k}_{g}.nc" for g, k in SOURCES.items()}
SFLUX_VARS = {g: list(m.values()) for g, m in ERA5_SFLUX_MAPPING.items()}
# avg: the 18 UTC run of the previous day covers the first hours of 2020-01-01
FIRST_DAY = {
    "instant": slice("2020-01-01T00", "2020-01-01T23"),
    "avg": slice("2019-12-31T18", "2020-01-01T18"),
}


def source(era5_dir: pathlib.Path, kind: str) -> pathlib.Path:
    return era5_dir / f"era5_n320_{START}_{DURATION}_{kind}.nc"


def to_sflux(file: pathlib.Path, group: str, output_dir: pathlib.Path, *extra: str) -> pathlib.Path:
    meteo("convert", "era5-to-sflux", "--file", file, "--group", group, "--output-dir", output_dir, "--overwrite", *extra)
    (out,) = output_dir.glob(f"sflux_*_{group}.nc")
    return out


@pytest.fixture(scope="session")
def era5_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[pathlib.Path]:
    # METEO_E2E_DIR: keep (and reuse) the downloaded N320 files between runs
    persistent = os.environ.get("METEO_E2E_DIR")
    path = pathlib.Path(persistent) / "era5" if persistent else tmp_path_factory.mktemp("era5")
    path.mkdir(parents=True, exist_ok=True)
    if not all(source(path, kind).exists() for kind in ("instant", "avg")):
        meteo("download", "era5", "--start-date", START, "--duration", DURATION, "--output-dir", path)
    yield path
    if not persistent:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def first_day(era5_dir: pathlib.Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, pathlib.Path]]:
    out_dir = tmp_path_factory.mktemp("era5_1day")
    files = {}
    for kind, window in FIRST_DAY.items():
        files[kind] = out_dir / f"era5_n320_{START}_P1D_{kind}.nc"
        with xr.open_dataset(source(era5_dir, kind)) as ds:
            tdim = "time" if "time" in ds.dims else "forecast_reference_time"
            ds.sel({tdim: window}).to_netcdf(files[kind])
    yield files
    shutil.rmtree(out_dir, ignore_errors=True)


@pytest.fixture
def scratch(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.parametrize("grid", ["n320", "O1280", "H32"])
def test_sflux_out_grid_must_be_rectilinear(scratch: pathlib.Path, grid: str) -> None:
    # fails on --out-grid validation, before the (dummy) input file is opened
    dummy = scratch / "era5_n320_20200101_P7D_instant.nc"
    dummy.touch()
    with pytest.raises(ValueError, match="not rectilinear"):
        to_sflux(dummy, "air", scratch, "--out-grid", grid)


@e2e
def test_regrid_default_is_0p1(first_day: dict[str, pathlib.Path], scratch: pathlib.Path) -> None:
    default = scratch / "regrid_default.nc"
    explicit = scratch / "regrid_0.1.nc"
    meteo("convert", "regrid", "--input-file", first_day["instant"], "--output-file", default)
    meteo("convert", "regrid", "--input-file", first_day["instant"], "--output-file", explicit, "--out-grid", "0.1")
    with xr.open_dataset(default) as a, xr.open_dataset(explicit) as b:
        assert (a.sizes["latitude"], a.sizes["longitude"]) == (1801, 3600)
        np.testing.assert_allclose(np.diff(a.longitude.values), 0.1, atol=1e-6)
        xr.testing.assert_equal(a, b)


@e2e
def test_regrid_0p25(first_day: dict[str, pathlib.Path], scratch: pathlib.Path) -> None:
    out = scratch / "regrid_0.25.nc"
    meteo("convert", "regrid", "--input-file", first_day["instant"], "--output-file", out, "--out-grid", "0.25")
    with xr.open_dataset(out) as ds:
        assert (ds.sizes["latitude"], ds.sizes["longitude"]) == (721, 1440)
        np.testing.assert_allclose(np.diff(ds.longitude.values), 0.25, atol=1e-6)


@e2e
@pytest.mark.parametrize("group", list(SOURCES))
def test_sflux_default_is_0p1(first_day: dict[str, pathlib.Path], scratch: pathlib.Path, group: str) -> None:
    out = to_sflux(first_day[SOURCES[group]], group, scratch)
    assert "_0.1x0.1_" in out.name
    with xr.open_dataset(out) as ds:
        lon, lat = ds.lon.values[0], ds.lat.values[:, 0]
        assert ds.sizes["ny_grid"] == 1801
        np.testing.assert_allclose(np.diff(lon), 0.1, atol=1e-6)
        np.testing.assert_allclose(np.diff(lat), 0.1, atol=1e-6)
        assert lat[0] == pytest.approx(-90) and lat[-1] == pytest.approx(90)
        assert lon[0] <= -180 and lon[-1] >= 180  # cyclic padding
        for var in SFLUX_VARS[group]:
            assert np.isfinite(ds[var].values).all(), var


@e2e
@pytest.mark.parametrize("group", list(WRONG_SOURCES))
def test_sflux_wrong_step_type_rejected(era5_dir: pathlib.Path, scratch: pathlib.Path, group: str) -> None:
    with pytest.raises(ValueError, match="Missing required variables"):
        to_sflux(source(era5_dir, WRONG_SOURCES[group]), group, scratch)
    assert not list(scratch.glob("sflux_*.nc"))


@e2e
@pytest.mark.parametrize("group", list(SOURCES))
def test_sflux_0p25_matches_reference(era5_dir: pathlib.Path, scratch: pathlib.Path, group: str) -> None:
    out = to_sflux(source(era5_dir, SOURCES[group]), group, scratch, "--out-grid", "0.25")
    assert "_0.25x0.25_" in out.name
    with xr.open_dataset(out) as generated, xr.open_dataset(fetch_reference(REFERENCES[group])) as ref:
        # native avg starts the day before: select the reference step, not the first one
        gen = generated.sel(time=ref.time.values, method="nearest", tolerance=np.timedelta64(1, "m"))
        # drop the polar rows (lat ±90): regrid edge values there are not comparable
        gen, ref = gen.isel(ny_grid=slice(1, -1)), ref.isel(ny_grid=slice(1, -1))
        np.testing.assert_allclose(gen.lon.values, ref.lon.values, atol=1e-6)
        np.testing.assert_allclose(gen.lat.values, ref.lat.values, atol=1e-6)
        for var in SFLUX_VARS[group]:
            assert_close(var, gen[var].values, ref[var].values)
