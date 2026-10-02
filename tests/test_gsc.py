"""Tests for the GSC skill. The Google API is mocked; nothing here hits the network."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from skills.gsc import client
from skills.gsc.__main__ import main

API_RESPONSE = {
    "rows": [
        {"keys": ["2026-07-01", "MOBILE"], "clicks": 100, "impressions": 2000, "ctr": 0.05, "position": 8.4},
        {"keys": ["2026-07-01", "DESKTOP"], "clicks": 40, "impressions": 500, "ctr": 0.08, "position": 5.1},
    ]
}


@pytest.fixture
def gsc(tmp_path, monkeypatch):
    """A configured environment with the Google API boundary mocked.

    Returns the mock of the API's ``query`` method, for inspecting what was sent.
    """
    sites = tmp_path / "sites.yaml"
    sites.write_text(
        "sites:\n"
        "  ressichem:\n"
        "    name: Ressichem\n"
        "    gsc_property: sc-domain:example.com\n",
        encoding="utf-8",
    )
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(client, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("SEO_ENGINE_SITES_CONFIG", str(sites))
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_FILE", str(key_file))
    monkeypatch.setattr(
        client.service_account.Credentials, "from_service_account_file", MagicMock()
    )

    service = MagicMock()
    query = service.searchanalytics.return_value.query
    query.return_value.execute.return_value = API_RESPONSE
    monkeypatch.setattr(client, "build", MagicMock(return_value=service))
    return query


def run(**overrides):
    kwargs = {"site": "ressichem", "start_date": "2026-07-01", "end_date": "2026-09-30"}
    kwargs.update(overrides)
    return client.query_search_analytics(**kwargs)


# --- Valid queries -----------------------------------------------------------


def test_valid_query_sends_expected_request(gsc):
    run(
        dimensions=["date", "device"],
        filters=[{"dimension": "country", "operator": "equals", "expression": "pak"}],
        row_limit=50,
    )

    gsc.assert_called_once_with(
        siteUrl="sc-domain:example.com",
        body={
            "startDate": "2026-07-01",
            "endDate": "2026-09-30",
            "dimensions": ["date", "device"],
            "rowLimit": 50,
            "dimensionFilterGroups": [
                {
                    "groupType": "and",
                    "filters": [{"dimension": "country", "operator": "equals", "expression": "pak"}],
                }
            ],
        },
    )


def test_result_echoes_request(gsc):
    result = run(dimensions=["date", "device"])

    assert result["request"] == {
        "site": "ressichem",
        "property": "sc-domain:example.com",
        "start_date": "2026-07-01",
        "end_date": "2026-09-30",
        "dimensions": ["date", "device"],
        "filters": [],
        "row_limit": 1000,
    }


def test_rows_are_flattened_by_dimension_name(gsc):
    result = run(dimensions=["date", "device"])

    assert result["row_count"] == 2
    assert result["rows"] == [
        {"date": "2026-07-01", "device": "MOBILE", "clicks": 100, "impressions": 2000, "ctr": 0.05, "position": 8.4},
        {"date": "2026-07-01", "device": "DESKTOP", "clicks": 40, "impressions": 500, "ctr": 0.08, "position": 5.1},
    ]


def test_no_dimensions_gives_single_aggregated_row(gsc):
    gsc.return_value.execute.return_value = {
        "rows": [{"clicks": 140, "impressions": 2500, "ctr": 0.056, "position": 7.7}]
    }

    result = run()

    assert result["rows"] == [{"clicks": 140, "impressions": 2500, "ctr": 0.056, "position": 7.7}]


def test_empty_api_response_gives_no_rows(gsc):
    gsc.return_value.execute.return_value = {}

    result = run(dimensions=["date"])

    assert result["rows"] == []
    assert result["row_count"] == 0


# --- Site resolution ---------------------------------------------------------


def test_alias_is_resolved_to_property(gsc):
    assert client.resolve_property("ressichem") == "sc-domain:example.com"


@pytest.mark.parametrize("raw", ["sc-domain:other.com", "https://www.other.com/"])
def test_raw_property_is_used_as_is(gsc, raw):
    result = run(site=raw)

    assert result["request"]["property"] == raw
    assert gsc.call_args.kwargs["siteUrl"] == raw


def test_raw_property_does_not_need_sites_config(gsc, monkeypatch, tmp_path):
    monkeypatch.setenv("SEO_ENGINE_SITES_CONFIG", str(tmp_path / "missing.yaml"))

    assert run(site="sc-domain:other.com")["request"]["property"] == "sc-domain:other.com"


def test_unknown_alias_is_rejected(gsc):
    with pytest.raises(ValueError, match="Unknown site alias 'nope'"):
        run(site="nope")


# --- Input validation --------------------------------------------------------


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "01-07-2026", "20260701", "yesterday", ""])
def test_invalid_date_is_rejected(gsc, bad):
    with pytest.raises(ValueError, match="start_date must be a valid YYYY-MM-DD date"):
        run(start_date=bad)
    gsc.assert_not_called()


def test_start_after_end_is_rejected(gsc):
    with pytest.raises(ValueError, match="is after end_date"):
        run(start_date="2026-09-30", end_date="2026-07-01")
    gsc.assert_not_called()


def test_unsupported_dimension_is_rejected(gsc):
    with pytest.raises(ValueError, match="Invalid dimensions"):
        run(dimensions=["date", "searchAppearance"])
    gsc.assert_not_called()


@pytest.mark.parametrize(
    "bad_filter",
    [
        {"dimension": "country", "operator": "equals"},
        {"dimension": "country", "operator": "equals", "expression": "pak", "extra": "x"},
        {"dimension": "browser", "operator": "equals", "expression": "chrome"},
        {"dimension": "country", "operator": "startsWith", "expression": "pa"},
        "country equals pak",
    ],
)
def test_malformed_filter_is_rejected(gsc, bad_filter):
    with pytest.raises(ValueError, match="filter"):
        run(filters=[bad_filter])
    gsc.assert_not_called()


@pytest.mark.parametrize("bad", [0, -1, 25001, "100", 10.5, True])
def test_invalid_row_limit_is_rejected(gsc, bad):
    with pytest.raises(ValueError, match="row_limit"):
        run(row_limit=bad)
    gsc.assert_not_called()


@pytest.mark.parametrize("ok", [1, 25000])
def test_row_limit_bounds_are_accepted(gsc, ok):
    assert run(row_limit=ok)["request"]["row_limit"] == ok


# --- Missing credentials / config --------------------------------------------


def test_missing_credentials_env_var(gsc, monkeypatch):
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_FILE")

    with pytest.raises(RuntimeError, match="GSC_SERVICE_ACCOUNT_FILE is not set"):
        run()


def test_missing_credentials_file(gsc, monkeypatch, tmp_path):
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_FILE", str(tmp_path / "absent.json"))

    with pytest.raises(FileNotFoundError, match="Service account key not found"):
        run()


def test_missing_sites_config(gsc, monkeypatch, tmp_path):
    monkeypatch.setenv("SEO_ENGINE_SITES_CONFIG", str(tmp_path / "missing.yaml"))

    with pytest.raises(FileNotFoundError, match="Sites config not found"):
        run()


def test_alias_without_property_is_rejected(gsc, monkeypatch, tmp_path):
    sites = tmp_path / "broken.yaml"
    sites.write_text("sites:\n  ressichem:\n    name: Ressichem\n", encoding="utf-8")
    monkeypatch.setenv("SEO_ENGINE_SITES_CONFIG", str(sites))

    with pytest.raises(ValueError, match="has no gsc_property"):
        run()


# --- CLI ---------------------------------------------------------------------

CLI_ARGS = ["--site", "ressichem", "--start-date", "2026-07-01", "--end-date", "2026-09-30"]


def test_cli_writes_json_to_stdout(gsc, capsys):
    exit_code = main(CLI_ARGS + ["--dimensions", "date", "device", "--row-limit", "50"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "request": {
            "site": "ressichem",
            "property": "sc-domain:example.com",
            "start_date": "2026-07-01",
            "end_date": "2026-09-30",
            "dimensions": ["date", "device"],
            "filters": [],
            "row_limit": 50,
        },
        "row_count": 2,
        "rows": [
            {"date": "2026-07-01", "device": "MOBILE", "clicks": 100, "impressions": 2000, "ctr": 0.05, "position": 8.4},
            {"date": "2026-07-01", "device": "DESKTOP", "clicks": 40, "impressions": 500, "ctr": 0.08, "position": 5.1},
        ],
    }


def test_cli_accepts_comma_separated_dimensions(gsc, capsys):
    main(CLI_ARGS + ["--dimensions", "date,device"])

    assert json.loads(capsys.readouterr().out)["request"]["dimensions"] == ["date", "device"]


def test_cli_passes_filters(gsc, capsys):
    main(CLI_ARGS + ["--filter", "country", "equals", "pak", "--filter", "page", "contains", "/blog/"])

    assert json.loads(capsys.readouterr().out)["request"]["filters"] == [
        {"dimension": "country", "operator": "equals", "expression": "pak"},
        {"dimension": "page", "operator": "contains", "expression": "/blog/"},
    ]


def test_cli_preserves_non_ascii_queries(gsc, capsys):
    gsc.return_value.execute.return_value = {
        "rows": [{"keys": ["واٹر پروفنگ"], "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 1.0}]
    }

    main(CLI_ARGS + ["--dimensions", "query"])

    assert json.loads(capsys.readouterr().out)["rows"][0]["query"] == "واٹر پروفنگ"


def test_cli_reports_errors_on_stderr_with_exit_code_1(gsc, capsys):
    exit_code = main(CLI_ARGS + ["--dimensions", "bogus"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid dimensions" in captured.err


def test_cli_reports_api_failure_without_traceback(gsc, capsys):
    gsc.return_value.execute.side_effect = RuntimeError("403 forbidden")

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "error: RuntimeError: 403 forbidden\n"


def test_cli_usage_error_exits_2(gsc, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--site", "ressichem"])

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


def test_cli_never_prints_credential_contents(gsc, tmp_path, capsys):
    key_file = tmp_path / "service-account.json"
    key_file.write_text('{"private_key": "SECRET-KEY-MATERIAL"}', encoding="utf-8")

    main(CLI_ARGS)
    gsc.return_value.execute.side_effect = RuntimeError("boom")
    main(CLI_ARGS)

    captured = capsys.readouterr()
    assert "SECRET-KEY-MATERIAL" not in captured.out + captured.err
