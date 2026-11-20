# meteo

Download meteorological / ocean forcing (ERA5, ECMWF IFS HRES from MARS, HYCOM, CMEMS) and convert it to
[SCHISM](https://schism-dev.github.io/schism/master/index.html) `sflux` files.

## Installation

```bash
git clone https://github.com/seareport/meteo
cd meteo
python3.13 -m venv .venv && source .venv/bin/activate
poetry install --with test --extras sflux     # add --extras complete for HYCOM/CMEMS
```

Regridding uses MIR through `earthkit-geo` (pip wheels `mir-python`/`eckit`, no metview needed).

Credentials:

| Source       | File / env                                           |
|--------------|------------------------------------------------------|
| ERA5 (CDS)   | `~/.cdsapirc` or `CDSAPI_URL` + `CDSAPI_KEY`         |
| MARS (HRES)  | `~/.ecmwfapirc`                                      |
| CMEMS        | `copernicusmarine login`                             |

## Concepts

- **Grid spec**: every `--grid` / `--out-grid` / `--in-grid` option takes either a Gaussian grid name
  (`N320`, `O1280`, `F1280`, …) or a regular lat/lon increment in degrees: `0.1`, `0.25`, or `dlon x dlat` like `0.25x0.5`.
- **Native first**: ERA5 is downloaded on its archived N320 reduced Gaussian grid and HRES on O1280, then
  regridded locally with MIR. The input grid is always inferred from the file.
- **Rectilinear sflux**: SCHISM sflux needs 1-D latitude/longitude, so sflux output grids must be regular
  lat/lon or regular Gaussian (`F*`). Reduced/octahedral/HEALPix targets are rejected.
- **File naming**: `{source}_{grid}_{start}_{duration}_{kind}.{nc,grib}`, e.g. `era5_n320_20200101_P7D_instant.nc`,
  `o1280_20240101_P31D_msl.grib`; sflux outputs are `sflux_{...}_{group}.nc` with `group` in `air`, `rad`, `prc`.
- **Time range**: `--start-date` plus either an exclusive `--end-date` or an ISO 8601 `--duration` (`P1D`, `P1M`, `P1M15D`).
- **ERA5 step types**: `instant` (u10, v10, t2m, d2m, msl → `air`) and `avg` (mean rates → `rad`, `prc`) are
  separate files, because their time axes differ (hourly vs forecast reference time × step).

## CLI

```bash
meteo --help
meteo download --help
meteo convert --help
```

### ERA5 → sflux

```bash
# native N320 (default); writes era5_n320_20200101_P7D_{instant,avg}.nc
meteo download era5 --start-date 20200101 --duration P7D --output-dir era5

# regridded and converted on the fly, 0.1 deg by default
meteo convert era5-to-sflux --file era5/era5_n320_20200101_P7D_instant.nc --group air
meteo convert era5-to-sflux --file era5/era5_n320_20200101_P7D_avg.nc     --group rad
meteo convert era5-to-sflux --file era5/era5_n320_20200101_P7D_avg.nc     --group prc

# other rectilinear grids
meteo convert era5-to-sflux --file era5/era5_n320_20200101_P7D_instant.nc --group air --out-grid 0.25
meteo convert era5-to-sflux --file era5/era5_n320_20200101_P7D_avg.nc     --group rad --out-grid 0.25x0.5
```

Outputs are named like `sflux_era5_0.1x0.1_20200101_P7D_instant_air.nc` and include longitude wrap-padding
across ±180°. ERA5 can also be requested pre-interpolated from CDS (`--grid 0.25`); `era5-to-sflux` skips
regridding when the input is already on the target grid.

### ECMWF HRES (MARS) → sflux

```bash
for var in 2d msl sp ssrd strd t2m tp u10 v10; do
  meteo download mars --start-date 20200501 --duration P1D --variable $var --output-dir ope_ecmwf/O1280
done
for group in air rad prc; do
  meteo convert mars-to-sflux --start-date 20200501 --duration P1D --group $group \
    --input-dir ope_ecmwf/O1280 --output-dir ope_ecmwf/F1280/sflux
done
```

`mars-to-sflux` finds the per-variable files by name under `--input-dir`. `sh2` is computed from `2d` + `sp`
when it is missing, and accumulated `ssrd`/`strd`/`tp` are de-accumulated to rates.

### Generic tools

```bash
meteo convert regrid --input-file in.nc --output-file out.nc --out-grid 0.25   # N320 -> 0.1 and O1280 -> F1280 are recognised automatically, no need to specify --out-grid
meteo convert normalize_lon in.nc out.nc --longitude-convention 360
meteo convert pad in.nc out.nc --pad-longitude --pad-latitude --pad-method-latitude fade
meteo download hycom 2024 1 11
meteo download cmems 2024 1 11 --output-format hycom
```

## Memory and disk

A global 0.1° float32 field is ~26 MB, so one week of hourly `air` (5 variables) is ~22 GB uncompressed.
Convert in short periods (`P7D`) at 0.1°. N320 ERA5 is ~3.6 GB (instant) + ~2.5 GB (avg) per week.
MIR interpolation weights are cached in `--mir-cache-path` / `MIR_CACHE_PATH`; the first regrid to a new grid pair is slower.

## Tests

E2E tests compare the first sflux time step with trusted reference files hosted on Zenodo
([record 23881590](https://zenodo.org/records/23881590)). They are downloaded on first use, md5-checked and cached in
`$METEO_E2E_DIR/reference` (default: the user cache dir, `meteo/e2e`).

```bash
pytest                                                    # fast tests; e2e skipped
METEO_E2E=1 pytest -s test/test_era5_sflux_e2e.py         # downloads ERA5 N320 2020-01-01 P7D from CDS (~6 GB)
METEO_E2E_MARS=1 pytest -s test/test_mars_sflux_e2e.py    # downloads MARS O1280 2020-01-01 P1D (~3 GB), ~8 GB peak disk (files are deleted between steps)
```

The ERA5 e2e test regrids N320 to 0.25°; the MARS one regrids O1280 to F1280 (`meteo convert mars-to-sflux`). The MARS test downloads and converts air first, deletes everything, then downloads the avg variables and converts rad, deletes the rad output and converts prc. In CI the ERA5 test runs weekly and the MARS test monthly (1st, 04:00 UTC), both also via manual dispatch. The MARS job needs the `ECMWF_API_KEY` and `ECMWF_API_EMAIL` secrets
