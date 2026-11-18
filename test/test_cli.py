import pytest

from meteo.__main__ import main_app


def test_meta_app_forwards_options_to_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    # Guards against the meta layer rejecting subcommand options as "Unknown option"
    # (cyclopts requires allow_leading_hyphen on the meta *tokens parameter).
    with pytest.raises(SystemExit):
        main_app.meta(["download", "mars", "--variable", "badvar", "--start-date", "20240101", "--duration", "P1M"])
    captured = capsys.readouterr()
    assert "Unknown option" not in captured.out + captured.err
    assert 'Invalid value "badvar"' in captured.out + captured.err
