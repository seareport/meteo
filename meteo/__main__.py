from __future__ import annotations

import logging
import os
import sys
from typing import Annotated

import logfmter
from cyclopts import App
from cyclopts import Parameter

from meteo._literals import L_LogLevel

download_app = App(name="download", help="Download data from the internet")
download_app.command("meteo._cli:cli_cmems", name="cmems")
download_app.command("meteo._cli:cli_download_era5", name="era5")
download_app.command("meteo._cli:cli_download_mars", name="mars")
download_app.command("meteo._cli:cli_hycom", name="hycom")

convert_app = App(name="convert", help="Convert data to other formats")
convert_app.command("meteo._cli:cli_convert_era5_to_sflux", name="era5-to-sflux")
convert_app.command("meteo._cli:cli_convert_mars_to_sflux", name="mars-to-sflux")
convert_app.command("meteo._cli:cli_convert_regrid", name="regrid")
convert_app.command("meteo._cli:cli_convert_normalize_lon", name="normalize_lon")
convert_app.command("meteo._cli:cli_convert_pad", name="pad")

main_app = App()
main_app.command(convert_app)
main_app.command(download_app)


def _setup_logging(level: str) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logfmter.Logfmter(
            keys=["name", "at"],
            mapping={"at": "levelname"},
        )
    )
    logging.basicConfig(level=level, handlers=[handler])
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("datashader").setLevel(logging.INFO)
    logging.getLogger("findlibs").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("gribapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("matplotlib").setLevel(logging.INFO)
    logging.getLogger("markdown_it").setLevel(logging.INFO)
    logging.getLogger("numba").setLevel(logging.INFO)
    logging.getLogger("numexpr").setLevel(logging.WARNING)


@main_app.meta.default
def _main_meta(
    *tokens: Annotated[str, Parameter(show=False)],
    log_level: Annotated[
        L_LogLevel, Parameter(name=["--log-level", "-l"], env_var="METEO_LOG_LEVEL", help="Root logger level")
    ] = "DEBUG",
) -> None:
    """meteo CLI."""
    _setup_logging(log_level)
    if os.environ.get("DEBUG", None):
        main_app(tokens, exit_on_error=False)
    else:
        main_app(tokens, exit_on_error=True)


def main() -> None:
    main_app.meta()
