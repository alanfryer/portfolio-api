import json
import logging
from unittest.mock import MagicMock, mock_open, patch, call
import pytest
import requests
from fastapi import HTTPException, status

# TODO: Update these imports to match your actual module structure
from services.weather_service import WeatherService, _session, GEOCODE_URL


@pytest.fixture
def service():
    return WeatherService()


@pytest.fixture
def mock_coords(service):
    with patch.object(service, "get_location_coordinates", return_value=(53.258, -2.518)) as mock:
        yield mock

@pytest.fixture
def mock_fetch():
  with patch("services.weather_service._fetch_open_meteo_coords") as mock:
    yield mock
    
# ---------------------------------------------------------------------------
# _load_weather_codes: Happy Path & Exception Handling
# ---------------------------------------------------------------------------

def test_load_weather_codes_success(caplog):
    """Loads and parses JSON weather codes from WEATHER_CODES_FILE."""
    sample_data = {"0": "Clear night", "1": "Sunny day", "7": "Cloudy"}
    mocked_file = mock_open(read_data=json.dumps(sample_data))

    with (
        caplog.at_level(logging.INFO),
        patch("services.weather_service.WEATHER_CODES_FILE", "/fake/path/weather_codes.json"),
        patch("builtins.open", mocked_file) as m_open,
    ):
        result = WeatherService._load_weather_codes()

    m_open.assert_called_once_with("/fake/path/weather_codes.json", "r", encoding="utf-8")
    assert result == sample_data
    assert "Loading weather codes from file /fake/path/weather_codes.json" in caplog.text


@pytest.mark.parametrize(
    "side_effect",
    [
        FileNotFoundError("No such file or directory"),
        PermissionError("Permission denied"),  # Subclass of OSError
        OSError("I/O error"),
    ],
)
def test_load_weather_codes_file_os_errors(caplog, side_effect):
    """Returns empty dict and logs an error when file cannot be opened or read."""
    with (
        caplog.at_level(logging.ERROR),
        patch("services.weather_service.WEATHER_CODES_FILE", "/missing/weather_codes.json"),
        patch("builtins.open", side_effect=side_effect),
    ):
        result = WeatherService._load_weather_codes()

    assert result == {}
    assert "Could not load weather codes from '/missing/weather_codes.json'" in caplog.text


def test_load_weather_codes_invalid_json(caplog):
    """Returns empty dict and logs an error when file contains malformed JSON."""
    mocked_file = mock_open(read_data="{invalid json content")

    with (
        caplog.at_level(logging.ERROR),
        patch("services.weather_service.WEATHER_CODES_FILE", "/fake/path/bad_codes.json"),
        patch("builtins.open", mocked_file),
    ):
        result = WeatherService._load_weather_codes()

    assert result == {}
    assert "Could not load weather codes from '/fake/path/bad_codes.json'" in caplog.text
    
def test_valid_weather_codes(service):
    """Verify known Met Office codes return their expected descriptions."""
    # Adjust these assertions to match the actual entries in your WEATHER_CODES dict
    assert WeatherService.get_weather_code(service, "0") == "Clear night"
    assert WeatherService.get_weather_code(service, "1") == "Sunny day"
    assert WeatherService.get_weather_code(service, "7") == "Cloudy"

def test_integer_input_coerced_to_string(service):
    """Ensure integer codes still match string keys due to str(code)."""
    assert WeatherService.get_weather_code(service, 1) == "Sunny day"

@pytest.mark.parametrize("invalid_code", [
    "999",          # Non-existent numeric string
    "invalid",      # Non-numeric string
    "",             # Empty string
    " 1 ",          # Unstripped whitespace
    None,           # NoneType (str(None) -> "None")
])
def test_unknown_and_edge_case_codes(service, invalid_code):
    """Verify unrecognized or malformed inputs return the fallback string."""
    assert WeatherService.get_weather_code(service, invalid_code) == "Unknown code"

def test_call_met_office_success(service):
    """Verify call_met_office builds the request properly and returns feature properties."""
    expected_properties = {
        "location": {"name": "Northwich"},
        "timeSeries": [{"time": "2026-11-27T11:00Z", "significantWeatherCode": 1}],
    }
    mock_api_response = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": expected_properties,
            }
        ],
    }

    # Mock the HTTP response object
    mock_response = MagicMock()
    mock_response.json.return_value = mock_api_response
    mock_response.raise_for_status.return_value = None

    with (
        patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key"),
        patch("services.weather_service.MET_OFFICE_URL", "https://metoffice.gov.uk"),
        patch.object(service, "get_location_coordinates", return_value=(53.2587, -2.5181)) as mock_coords,
        patch("services.weather_service._session.get", return_value=mock_response) as mock_get,
    ):
        result = service.call_met_office(location="Northwich", timesteps="/hourly")

    # 1. Assert the returned dictionary matches the nested 'properties' object
    assert result == expected_properties

    # 2. Assert coordinate lookup was called with the right location
    mock_coords.assert_called_once_with("Northwich")

    # 3. Assert _session.get was called with stripped slash, headers, params, and timeout
    mock_get.assert_called_once_with(
        "https://metoffice.gov.uk/hourly",
        headers={
            "accept": "application/json",
            "apikey": "test-api-key",
        },
        params={
            "excludeParameterMetadata": "TRUE",
            "includeLocationName": "TRUE",
            "latitude": 53.2587,
            "longitude": -2.5181,
        },
        timeout=5.0,
    )
    mock_response.raise_for_status.assert_called_once()
# ---------------------------------------------------------------------------
# 1. Pre-request Validation Exceptions
# ---------------------------------------------------------------------------

@patch("services.weather_service.MET_OFFICE_API_KEY", "")
def test_call_met_office_missing_api_key(service):
    """Raises 500 if MET_OFFICE_API_KEY is missing or empty."""
    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "Weather service API key is not configured."


@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
def test_call_met_office_invalid_location(service):
    """Propagates HTTPException raised by get_location_coordinates."""
    with patch.object(
        service,
        "get_location_coordinates",
        side_effect=HTTPException(status_code=400, detail="Invalid location"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.call_met_office("InvalidCity123", "hourly")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid location"


# ---------------------------------------------------------------------------
# 2. Response Payload Validation Exceptions
# ---------------------------------------------------------------------------

@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get")
def test_call_met_office_response_not_dict(mock_get, service, mock_coords):
    """Raises 502 if the JSON root is not a dictionary (e.g., a list)."""
    mock_response = MagicMock()
    mock_response.json.return_value = ["unexpected", "list"]
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "Expected response to be a dictionary, got list." in exc_info.value.detail


@pytest.mark.parametrize("invalid_features", [None, [], "not-a-list", {}])
@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get")
def test_call_met_office_missing_or_invalid_features(
    mock_get, service, mock_coords, invalid_features
):
    """Raises 404 if 'features' is missing, empty, or not a list."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"features": invalid_features}
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "No forecast features returned for 'Northwich'."


@pytest.mark.parametrize("invalid_properties", [None, "not-a-dict", ["list"]])
@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get")
def test_call_met_office_missing_or_invalid_properties(
    mock_get, service, mock_coords, invalid_properties
):
    """Raises an HTTPException if features[0]['properties'] is missing or not a dict."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"features": [{"properties": invalid_properties}]}
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    # Adjust status_code assertion if your truncated block raises 502 instead of 404
    assert exc_info.value.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_502_BAD_GATEWAY,
    )
    assert "Missing or invalid 'properties' object in forecast feature." in exc_info.value.detail


# ---------------------------------------------------------------------------
# 3. Network & HTTP Request Exceptions (from the try/except block)
# ---------------------------------------------------------------------------

@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get", side_effect=requests.exceptions.Timeout("Timed out"))
def test_call_met_office_timeout(mock_get, service, mock_coords):
    """Handles requests.exceptions.Timeout appropriately."""
    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code in (
        status.HTTP_504_GATEWAY_TIMEOUT,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get")
def test_call_met_office_http_error(mock_get, service, mock_coords):
    """Handles non-2xx HTTP responses triggered by response.raise_for_status()."""
    mock_response = MagicMock()
    http_err = requests.exceptions.HTTPError("401 Unauthorized")
    http_err.response = MagicMock(status_code=401, text="Invalid API Key")
    mock_response.raise_for_status.side_effect = http_err
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code >= 400


@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get")
def test_call_met_office_invalid_json(mock_get, service, mock_coords):
    """Handles malformed JSON responses from the upstream API."""
    mock_response = MagicMock()
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code in (
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@patch("services.weather_service.MET_OFFICE_API_KEY", "test-api-key")
@patch.object(_session, "get", side_effect=requests.exceptions.ConnectionError("DNS failure"))
def test_call_met_office_request_exception(mock_get, service, mock_coords):
    """Handles generic requests.exceptions.RequestException errors."""
    with pytest.raises(HTTPException) as exc_info:
        service.call_met_office("Northwich", "hourly")

    assert exc_info.value.status_code in (
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )
    
# ---------------------------------------------------------------------------
# 1. Happy Path & Caching
# ---------------------------------------------------------------------------

@patch.object(_session, "get")
def test_get_location_coordinates_success(mock_get, service):
    """Returns (lat, lon) tuple as floats and strips whitespace from input."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [{"latitude": 53.258, "longitude": -2.518}]
    }
    mock_get.return_value = mock_response

    lat, lon = service.get_location_coordinates("  Northwich  ")

    assert (lat, lon) == (53.258, -2.518)
    assert isinstance(lat, float)
    assert isinstance(lon, float)
    mock_get.assert_called_once_with(
        GEOCODE_URL,
        params={
            "name": "Northwich",
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=5.0,
    )




# ---------------------------------------------------------------------------
# 2. Input & Empty Results Exceptions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("empty_input", ["", "   ", "\t\n"])
@patch.object(_session, "get")
def test_get_location_coordinates_empty_input(mock_get, service, empty_input):
    """Raises 400 Bad Request when location is empty or whitespace-only."""
    with pytest.raises(HTTPException) as exc_info:
        service.get_location_coordinates(empty_input)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Location parameter cannot be empty."
    mock_get.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"results": []}, {"results": None}])
@patch.object(_session, "get")
def test_get_location_coordinates_no_results(mock_get, service, payload):
    """Raises 404 Not Found when API returns no matching results."""
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        service.get_location_coordinates("Atlantis")

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "No coordinates found for location 'Atlantis'."

@pytest.mark.parametrize("empty_input", ["", "   ", "\t\n"])
def test_empty_location_raises_400(service, mock_fetch, empty_input):
    with pytest.raises(HTTPException) as exc_info:
        service.get_location_coordinates(empty_input)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Location parameter cannot be empty."
    mock_fetch.assert_not_called()

def test_not_found_raises_404(service, mock_fetch):
  mock_fetch.return_value = None

  with pytest.raises(HTTPException) as exc_info:
    service.get_location_coordinates("Atlantis")

  assert exc_info.value.status_code == 404
  assert "No coordinates found for location 'Atlantis'" in exc_info.value.detail


# --- Upstream & Network Errors (5xx) ---


def test_timeout_raises_504(service, mock_fetch):
  mock_fetch.side_effect = requests.Timeout("Read timed out")

  with pytest.raises(HTTPException) as exc_info:
    service.get_location_coordinates("London")

  assert exc_info.value.status_code == 504
  assert "Geocoding request timed out for 'London'" in exc_info.value.detail


def test_http_error_with_response_raises_502(service, mock_fetch):
  mock_response = MagicMock()
  mock_response.status_code = 503
  mock_fetch.side_effect = requests.HTTPError(
      "Service Unavailable", response=mock_response
  )

  with pytest.raises(HTTPException) as exc_info:
    service.get_location_coordinates("Manchester")

  assert exc_info.value.status_code == 502
  assert (
      "Geocoding API HTTP error (503) for 'Manchester'" in exc_info.value.detail
  )


def test_http_error_without_response_raises_502(service, mock_fetch):
  # Tests the `e.response is not None else "Unknown"` fallback branch
  mock_fetch.side_effect = requests.HTTPError("Error without response")

  with pytest.raises(HTTPException) as exc_info:
    service.get_location_coordinates("Manchester")

  assert exc_info.value.status_code == 502
  assert (
      "Geocoding API HTTP error (Unknown) for 'Manchester'"
      in exc_info.value.detail
  )


def test_generic_request_exception_raises_502(service, mock_fetch):
  mock_fetch.side_effect = requests.ConnectionError("DNS resolution failed")

  with pytest.raises(HTTPException) as exc_info:
    service.get_location_coordinates("Edinburgh")

  assert exc_info.value.status_code == 502
  assert "Network error geocoding 'Edinburgh'" in exc_info.value.detail


@pytest.mark.parametrize(
    "exc_type",
    [
        ValueError("invalid float"),
        KeyError("latitude"),
        TypeError("NoneType is not subscriptable"),
    ],
)
def test_payload_parsing_errors_raise_502(service, mock_fetch, exc_type):
    mock_fetch.side_effect = exc_type

    with pytest.raises(HTTPException) as exc_info:
        service.get_location_coordinates("Cardiff")

    assert exc_info.value.status_code == 502
    assert (
        "Unexpected geocoding payload structure for 'Cardiff'"
        in exc_info.value.detail
    )

# ---------------------------------------------------------------------------
# 1. Happy Path & Formatting
# ---------------------------------------------------------------------------

def test_get_hourly_forecast_success(service):
    """Returns formatted forecast dict when date and hour match an entry in timeSeries."""
    target_entry = {
        "time": "2026-11-25T14:00Z",
        "screenTemperature": 12.5,
        "feelsLikeTemperature": 10.2,
        "windSpeed10m": 15,
        "windDirectionFrom10m": 180,
        "windGustSpeed10m": 24,
        "probOfPrecipitation": 20,
        "screenRelativeHumidity": 82,
        "visibility": 10000,
        "significantWeatherCode": 7,
    }
    mock_forecast = {
        "location": {"name": "Northwich Station"},
        "timeSeries": [
            {"time": "2026-11-25T13:00Z"},  # Wrong hour (should skip)
            target_entry,
        ],
    }

    with (
        patch.object(service, "call_met_office", return_value=mock_forecast) as mock_call,
        patch.object(service, "degrees_to_compass", return_value="S") as mock_compass,
        patch.object(service, "get_weather_code", return_value="Cloudy") as mock_code,
    ):
        result = service.get_hourly_forecast("Northwich", "25-11-2026", 14)

    mock_call.assert_called_once_with("Northwich", "hourly")
    mock_compass.assert_called_once_with(180.0)
    mock_code.assert_called_once_with("7")

    assert result == {
        "location": "Northwich",
        "met_location": "Northwich Station",
        "date": "2026-11-25T14:00Z",
        "summary": (
            "Cloudy, Temperature: 12.5, Feels like 10.2, "
            "Wind: Speed 15mph, Direction S, Gust 24mph, "
            "Precipitation: 20%, Humidity: 82%, Visibility: 10000m"
        ),
        "timeSeries": [target_entry],
    }


def test_get_hourly_forecast_defaults_missing_optional_fields(service):
    """Falls back to 'Unknown station', 'Unknown' weather, and 'N/A' when optional keys are omitted."""
    target_entry = {
        "time": "2026-11-25T09:00Z",
        "windDirectionFrom10m": 90,  # Required as float() in current code (see bug note below)
    }
    mock_forecast = {
        "location": None,
        "timeSeries": [target_entry],
    }

    with (
        patch.object(service, "call_met_office", return_value=mock_forecast),
        patch.object(service, "degrees_to_compass", return_value="E"),
        patch.object(service, "get_weather_code") as mock_code,
    ):
        result = service.get_hourly_forecast("Northwich", "25-11-2026", 9)

    mock_code.assert_not_called()
    assert result["met_location"] == "Unknown station"
    assert result["summary"] == (
        "Unknown, Temperature: N/A, Feels like N/A, "
        "Wind: Speed N/Amph, Direction E, Gust N/Amph, "
        "Precipitation: N/A%, Humidity: N/A%, Visibility: N/Am"
    )


# ---------------------------------------------------------------------------
# 2. Timestamp Parsing & Filtering Edge Cases
# ---------------------------------------------------------------------------

def test_get_hourly_forecast_skips_malformed_timestamps(service):
    """Skips entries with missing, non-string, or unparseable 'time' values and finds valid match."""
    valid_entry = {
        "time": "2026-11-25T15:00Z",
        "windDirectionFrom10m": 270,
        "significantWeatherCode": 1,
    }
    mock_forecast = {
        "location": {"name": "Northwich"},
        "timeSeries": [
            {},                                # KeyError: missing 'time'
            {"time": None},                    # TypeError: strptime expected str
            {"time": "not-a-valid-timestamp"}, # ValueError: bad format
            valid_entry,
        ],
    }

    with (
        patch.object(service, "call_met_office", return_value=mock_forecast),
        patch.object(service, "degrees_to_compass", return_value="W"),
        patch.object(service, "get_weather_code", return_value="Sunny"),
    ):
        result = service.get_hourly_forecast("Northwich", "25-11-2026", 15)

    assert result["date"] == "2026-11-25T15:00Z"
    assert result["timeSeries"] == [valid_entry]


# ---------------------------------------------------------------------------
# 3. Exceptions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "time_series",
    [
        [],                                  # Empty timeSeries
        [{"time": "2026-11-26T14:00Z"}],     # Wrong date
        [{"time": "2026-11-25T13:00Z"}],     # Wrong hour
        [{"time": "invalid-date"}],          # All entries skipped
    ],
)
def test_get_hourly_forecast_not_found_raises_404(service, time_series):
    """Raises 404 Not Found when no timeSeries entry matches target_date and target_hour."""
    mock_forecast = {
        "location": {"name": "Northwich"},
        "timeSeries": time_series,
    }

    with patch.object(service, "call_met_office", return_value=mock_forecast):
        with pytest.raises(HTTPException) as exc_info:
            service.get_hourly_forecast("Northwich", "25-11-2026", 14)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "No forecast found matching 25-11-2026 at 14."


def test_get_hourly_forecast_propagates_call_met_office_exception(service):
    """Propagates HTTPException raised by self.call_met_office."""
    with patch.object(
        service,
        "call_met_office",
        side_effect=HTTPException(status_code=502, detail="Upstream error"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.get_hourly_forecast("Northwich", "25-11-2026", 14)

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert exc_info.value.detail == "Upstream error"
    
# ---------------------------------------------------------------------------
# 1. get_daily_forecast: Happy Path & Defaults
# ---------------------------------------------------------------------------

def test_get_daily_forecast_success(service):
    """Returns formatted day/night forecast summaries when target_date matches."""
    target_entry = {
        "time": "2026-11-25T00:00Z",
        "dayMaxScreenTemperature": 14.0,
        "nightMinScreenTemperature": 6.5,
        "dayMaxFeelsLikeTemp": 12.0,
        "nightMinFeelsLikeTemp": 4.0,
        "midday10MWindSpeed": 12,
        "midnight10MWindSpeed": 8,
        "midday10MWindDirection": 180,
        "midnight10MWindDirection": 270,
        "midday10MWindGust": 20,
        "midnight10MWindGust": 14,
        "dayProbabilityOfPrecipitation": 10,
        "nightProbabilityOfPrecipitation": 40,
        "middayRelativeHumidity": 75,
        "midnightRelativeHumidity": 90,
        "middayVisibility": 15000,
        "midnightVisibility": 8000,
        "daySignificantWeatherCode": 1,
        "nightSignificantWeatherCode": 12,
    }
    mock_forecast = {
        "location": {"name": "Northwich Station"},
        "timeSeries": [
            {"time": "2026-11-24T00:00Z"},  # Wrong date (should skip)
            target_entry,
        ],
    }

    with (
        patch.object(service, "call_met_office", return_value=mock_forecast) as mock_call,
        patch.object(service, "degrees_to_compass", side_effect=["S", "W"]) as mock_compass,
        patch.object(service, "get_weather_code", side_effect=["Sunny", "Light rain"]) as mock_code,
    ):
        result = service.get_daily_forecast("Northwich", "25-11-2026")

    mock_call.assert_called_once_with("Northwich", "daily")
    assert mock_compass.call_args_list == [call(180.0), call(270.0)]
    assert mock_code.call_args_list == [call("1"), call("12")]

    assert result == {
        "location": "Northwich",
        "met_location": "Northwich Station",
        "date": "2026-11-25T00:00Z",
        "summary": [
            {
                "day": (
                    "Sunny, Temperature: 14.0, Feels like 12.0, "
                    "Wind: Speed 12mph, Direction S, Gust 20mph, "
                    "Precipitation: 10%, Humidity: 75%, Visibility: 15000m"
                )
            },
            {
                "night": (
                    "Light rain, Temperature: 6.5, Feels like 4.0, "
                    "Wind: Speed 8mph, Direction W, Gust 14mph, "
                    "Precipitation: 40%, Humidity: 90%, Visibility: 8000m"
                )
            },
        ],
        "timeSeries": [target_entry],
    }


def test_get_daily_forecast_defaults_missing_optional_fields(service):
    """Falls back to 'Unknown station', 'Unknown', and 'N/A' when optional fields are omitted."""
    target_entry = {"time": "2026-11-25T00:00Z"}
    mock_forecast = {
        "location": None,
        "timeSeries": [target_entry],
    }

    with (
        patch.object(service, "call_met_office", return_value=mock_forecast),
        patch.object(service, "degrees_to_compass") as mock_compass,
        patch.object(service, "get_weather_code") as mock_code,
    ):
        result = service.get_daily_forecast("Northwich", "25-11-2026")

    mock_compass.assert_not_called()
    mock_code.assert_not_called()

    expected_na_summary = (
        "Unknown, Temperature: N/A, Feels like N/A, "
        "Wind: Speed N/Amph, Direction N/A, Gust N/Amph, "
        "Precipitation: N/A%, Humidity: N/A%, Visibility: N/Am"
    )
    assert result["met_location"] == "Unknown station"
    assert result["summary"] == [
        {"day": expected_na_summary},
        {"night": expected_na_summary},
    ]


# ---------------------------------------------------------------------------
# 2. get_daily_forecast: Timestamp Parsing & Exceptions
# ---------------------------------------------------------------------------

def test_get_daily_forecast_skips_malformed_timestamps(service):
    """Skips entries with missing, None, or invalid timestamps and matches valid entry."""
    valid_entry = {"time": "2026-11-25T00:00Z"}
    mock_forecast = {
        "location": {"name": "Northwich"},
        "timeSeries": [
            {},                                # KeyError
            {"time": None},                    # TypeError
            {"time": "invalid-date-format"},   # ValueError
            valid_entry,
        ],
    }

    with patch.object(service, "call_met_office", return_value=mock_forecast):
        result = service.get_daily_forecast("Northwich", "25-11-2026")

    assert result["date"] == "2026-11-25T00:00Z"
    assert result["timeSeries"] == [valid_entry]


@pytest.mark.parametrize(
    "time_series",
    [
        [],                                # Empty timeSeries
        [{"time": "2026-11-26T00:00Z"}],   # Non-matching date
        [{"time": "bad-timestamp"}],       # All entries malformed
    ],
)
def test_get_daily_forecast_not_found_raises_404(service, time_series):
    """Raises 404 Not Found when no timeSeries entry matches target_date."""
    mock_forecast = {
        "location": {"name": "Northwich"},
        "timeSeries": time_series,
    }

    with patch.object(service, "call_met_office", return_value=mock_forecast):
        with pytest.raises(HTTPException) as exc_info:
            service.get_daily_forecast("Northwich", "25-11-2026")

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "No forecast found matching 25-11-2026."


def test_get_daily_forecast_propagates_call_met_office_exception(service):
    """Propagates HTTPException raised by self.call_met_office."""
    with patch.object(
        service,
        "call_met_office",
        side_effect=HTTPException(status_code=503, detail="Service unavailable"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.get_daily_forecast("Northwich", "25-11-2026")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "Service unavailable"


# ---------------------------------------------------------------------------
# 3. degrees_to_compass: Cardinal Directions, Wraparound & None
# ---------------------------------------------------------------------------

def test_degrees_to_compass_none():
    """Returns None when degrees is None."""
    assert WeatherService.degrees_to_compass(None) is None


@pytest.mark.parametrize(
    "degrees, expected",
    [
        (0, "N"),
        (22.5, "NNE"),
        (45, "NE"),
        (67.5, "ENE"),
        (90, "E"),
        (112.5, "ESE"),
        (135, "SE"),
        (157.5, "SSE"),
        (180, "S"),
        (202.5, "SSW"),
        (225, "SW"),
        (247.5, "WSW"),
        (270, "W"),
        (292.5, "WNW"),
        (315, "NW"),
        (337.5, "NNW"),
        # Wraparound & boundary cases
        (360, "N"),
        (359.9, "N"),
        (720, "N"),
        (-90, "W"),
        (-45, "NW"),
    ],
)
def test_degrees_to_compass_directions(degrees, expected):
    """Maps 16-point compass bearings accurately, including 360° wraparound and negative angles."""
    assert WeatherService.degrees_to_compass(degrees) == expected