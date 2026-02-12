# AGENTS.md — meteo

Guidance for coding agents working on this repo. User-facing docs are in `README.md`; the decision log is in `DECISIONS.md` (read it before changing CLI names, grids or file naming).

## Layout
- `meteo/__main__.py`: cyclopts app (`meteo download …`, `meteo convert …`) mapping commands to `_cli.py`.
- `meteo/_cli.py`: thin CLI wrappers. Imports are lazy (inside functions), and the docstrings are the `--help` text, so keep them in sync with behaviour.
- `meteo/_ecmwf.py`: ERA5 (earthkit-data `cds` source) and MARS downloads.
- `meteo/_convert.py`: `regrid` (file level) and `regrid_dataset` (lazy dask MIR regrid onto rectilinear grids), plus lon normalisation and padding.
- `meteo/_sflux.py`: ERA5/MARS → SCHISM sflux.
- `meteo/_utils.py`: grid parsing/inference (`parse_grid`, `infer_grid`, `rectilinear_grid`, `grid_slug`), padding, naming, I/O.
- `meteo/_constants.py`, `meteo/_literals.py`: variable maps, sflux attributes, CLI literals.
- `test/`: pytest. `test_era5_sflux_e2e.py` is gated by `METEO_E2E=1`.

## Conventions
- Python 3.13, poetry. Imports are one per line (`reorder-python-imports` pre-commit hook).
- Type hints; no new docstrings in library code except CLI functions (they are the help text). Use a short `#` comment only where something is non-obvious.
- Use vectorised xarray/numpy and keep large data lazy (dask). Preserve CF attributes and units.
- Grid specs are always dicts like `{"grid": "N320"}` or `{"grid": [dlon, dlat]}` (optional `"area": [N, W, S, E]`), parsed from strings via `parse_grid`.
- File names carry the grid slug (`n320`, `0.25x0.25`, `f1280`), and sflux names end with `_{air|rad|prc}.nc`.

## Gotchas (verified, do not regress)
- `earthkit.geo.regrid` on xarray objects crashes in earthkit-geo 1.2.0 (`'_eckit_geo.Grid' has no attribute 'copy'`). Use `regrid_dataset`, which calls `earthkit.geo.grids.array.regrid` per 2-D field.
- MIR assumes that a regular lat/lon input without an `area` starts at lon 0, N→S. Inputs in −180..180 or S→N come out shifted or flipped unless they are sorted and the `area` is passed (`regrid_dataset` does this).
- A bare octahedral in_grid (`O1280` without `area`) produces a 180° longitude shift. Grids inferred from files are fine.
- ERA5 native `avg` starts one day early (06/18 UTC runs, steps 1–12), and averaged values are timestamped at mid-hour (−30 min).
- sflux: lat S→N, `time:base_date` int32, `units = days since base_date`, plus `sflux_inputs.txt` next to the files.
- `reanalysis-era5-complete` (CDS) only serves N320: send one flat request per stepType and no `grid` key.

## Working rules
- Do not launch CDS/MARS downloads, multi-GB conversions or the e2e suite on your own. Hand the commands to the maintainer.
- After changes, run `pytest` (fast tests only) and `python -m py_compile` on touched files.
- For numerical changes, check magnitudes, units and NaN handling, not just that the code runs.
- Record lasting decisions in `DECISIONS.md`.
