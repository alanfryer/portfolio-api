from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

# TODO: Update 'your_router_module' to match the actual path of your router file
from routers.weather import get_weather_service, router


@pytest.fixture
def mock_weather_service():
    return MagicMock()


@pytest.fixture
def client(mock_weather_service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_weather_service] = lambda: mock_weather_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. GET /v1/weather/hourly
# ---------------------------------------------------------------------------

def test_get_hourly_forecast_endpoint_success(client, mock_weather_service):
    """Returns 200 and JSON forecast payload when query params are valid."""
    expected_payload = {
        "location": "Northwich",
        "met_location": "Northwich Station",
        "date": "2026-11-25T14:00Z",
        "summary": "Cloudy, Temperature: 12.5...",
        "timeSeries": [{"time": "2026-11-25T14:00Z"}],
    }
    mock_weather_service.get_hourly_forecast.return_value = expected_payload

    response = client.get(
        "/v1/weather/hourly",
        params={"location": "Northwich", "date": "25-11-2026", "hour": 14},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_payload
    mock_weather_service.get_hourly_forecast.assert_called_once_with(
        "Northwich", "25-11-2026", 14
    )


@pytest.mark.parametrize(
    "params",
    [
        {"date": "25-11-2026", "hour": 14},           # Missing location
        {"location": "Northwich", "hour": 14},       # Missing date
        {"location": "Northwich", "date": "25-11-2026"},  # Missing hour
        {"location": "Northwich", "date": "25-11-2026", "hour": "not-an-int"},  # Invalid hour type
    ],
)
def test_get_hourly_forecast_endpoint_validation_error(client, mock_weather_service, params):
    """Returns 422 Unprocessable Entity when required query params are missing or invalid."""
    response = client.get("/v1/weather/hourly", params=params)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    mock_weather_service.get_hourly_forecast.assert_not_called()


@pytest.mark.parametrize(
    "status_code, detail",
    [
        (status.HTTP_400_BAD_REQUEST, "Location parameter cannot be empty."),
        (status.HTTP_404_NOT_FOUND, "No forecast found matching 25-11-2026 at 14."),
        (status.HTTP_502_BAD_GATEWAY, "Upstream Met Office error"),
        (status.HTTP_504_GATEWAY_TIMEOUT, "Geocoding request timed out"),
    ],
)
def test_get_hourly_forecast_endpoint_propagates_http_exceptions(
    client, mock_weather_service, status_code, detail
):
    """Propagates HTTPException status codes and details raised by WeatherService."""
    mock_weather_service.get_hourly_forecast.side_effect = HTTPException(
        status_code=status_code, detail=detail
    )

    response = client.get(
        "/v1/weather/hourly",
        params={"location": "Northwich", "date": "25-11-2026", "hour": 14},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


# ---------------------------------------------------------------------------
# 2. GET /v1/weather/daily
# ---------------------------------------------------------------------------

def test_get_daily_forecast_endpoint_success(client, mock_weather_service):
    """Returns 200 and JSON daily forecast payload when query params are valid."""
    expected_payload = {
        "location": "Northwich",
        "met_location": "Northwich Station",
        "date": "2026-11-25T00:00Z",
        "summary": [{"day": "Sunny..."}, {"night": "Clear..."}],
        "timeSeries": [{"time": "2026-11-25T00:00Z"}],
    }
    mock_weather_service.get_daily_forecast.return_value = expected_payload

    response = client.get(
        "/v1/weather/daily",
        params={"location": "Northwich", "date": "25-11-2026"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_payload
    mock_weather_service.get_daily_forecast.assert_called_once_with(
        "Northwich", "25-11-2026"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"date": "25-11-2026"},        # Missing location
        {"location": "Northwich"},     # Missing date
        {},                            # Missing both
    ],
)
def test_get_daily_forecast_endpoint_validation_error(client, mock_weather_service, params):
    """Returns 422 Unprocessable Entity when required query params are missing."""
    response = client.get("/v1/weather/daily", params=params)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    mock_weather_service.get_daily_forecast.assert_not_called()


@pytest.mark.parametrize(
    "status_code, detail",
    [
        (status.HTTP_400_BAD_REQUEST, "Location parameter cannot be empty."),
        (status.HTTP_404_NOT_FOUND, "No forecast found matching 25-11-2026."),
        (status.HTTP_502_BAD_GATEWAY, "Upstream Met Office error"),
    ],
)
def test_get_daily_forecast_endpoint_propagates_http_exceptions(
    client, mock_weather_service, status_code, detail
):
    """Propagates HTTPException status codes and details raised by WeatherService."""
    mock_weather_service.get_daily_forecast.side_effect = HTTPException(
        status_code=status_code, detail=detail
    )

    response = client.get(
        "/v1/weather/daily",
        params={"location": "Northwich", "date": "25-11-2026"},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


# ---------------------------------------------------------------------------
# 3. Dependency Provider
# ---------------------------------------------------------------------------

def test_get_weather_service_returns_instance():
    """Verifies get_weather_service dependency factory returns a WeatherService instance."""
    from services.weather_service import WeatherService

    instance = get_weather_service()
    assert isinstance(instance, WeatherService)
