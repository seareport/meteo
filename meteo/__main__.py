from __future__ import annotations

import dataclasses
import logging
import os
import pathlib
import sys
import logfmter
from cyclopts import App

download_app = App(name="download", help="Download data from the internet")
download_app.command("meteo._cli:cli_cmems", name="cmems")
download_app.command("meteo._cli:cli_download_era5", name="era5")
download_app.command("meteo._cli:cli_download_o1280", name="o1280")
download_app.command("meteo._cli:cli_hycom", name="hycom")

convert_app = App(name="convert", help="Convert data to other formats")
convert_app.command("meteo._cli:cli_convert_era5_to_sflux", name="era5-to-sflux")
convert_app.command("meteo._cli:cli_convert_f1280_to_sflux", name="to-sflux")
convert_app.command("meteo._cli:cli_convert_o1280_to_f1280", name="to-f1280")

main_app = App()
main_app.command(convert_app)
main_app.command(download_app)


def main():
    # Logging
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logfmter.Logfmter(
            keys=["name", "at"],
            mapping={"at": "levelname"},
        )
    )
    logging.basicConfig(level=10, handlers=[handler])
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

    if os.environ.get("DEBUG", None):
        main_app(exit_on_error=False)
    else:
        main_app(exit_on_error=True)
