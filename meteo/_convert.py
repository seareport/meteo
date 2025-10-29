import os
import pathlib


def o1280_to_f1280(
    o1280_path: pathlib.Path,
    f1280_path: pathlib.Path,
    mir_cache_path: pathlib.Path | None = None,
    metview_tmp_path : pathlib.Path | None = None,
    mars_maxforks : int | None = None,
    ) -> None:
    # Set env variables before importing metview
    if mir_cache_path is not None:
        mir_cache_path.mkdir(parents=True, exist_ok=True)
        os.environ["MIR_CACHE_PATH"] = str(mir_cache_path)
    if metview_tmp_path is not None:
        metview_tmp_path.mkdir(parents=True, exist_ok=True)
        os.environ["METVIEW_TMPDIR"] = str(metview_tmp_path)
    if mars_maxforks is not None:
        os.environ["MARS_MAXFORKS"] = str(mars_maxforks)

    # Now import metview
    import metview as mv

    o1280_path.parent.mkdir(parents=True, exist_ok=True)
    f1280_path.parent.mkdir(parents=True, exist_ok=True)

    fgs = mv.read(source=str(o1280_path), grid="F1280")
    mv.write(str(f1280_path), fgs)
