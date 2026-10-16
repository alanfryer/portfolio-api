import pytest
from fastapi.testclient import TestClient
from fastapi import APIRouter, FastAPI, status

# Corrected imports matching your layout
from routers.exchange_rates import router
from services.authorization_service import authenticate
from services.exchange_rate_service import ExchangeRateService
from routers.exchange_rates import router, get_exchange_rate_service
# Create a clean FastAPI instance for testing
app = FastAPI()
app.include_router(router)

client = TestClient(app)


# 1. Create a mock for the authentication dependency
def mock_authenticate():
    return {"username": "test_user"}


# 2. Apply the dependency override before the tests run
@pytest.fixture(autouse=True)
def setup_dependencies():
    # Override the authentication dependency to simulate a logged-in user
    app.dependency_overrides[authenticate] = mock_authenticate
    yield
    # Clean up overrides after the test finishes
    app.dependency_overrides.clear()
    
def test_router_initialization():
    """
    Test that the APIRouter instance is initialized correctly.
    """
    # Assert
    assert isinstance(router, APIRouter)


def test_get_exchange_rate_service_provider():
    """
    Test that the dependency injection factory function instantiates 
    and returns a valid instance of ExchangeRateService.
    """
    # Act
    service_instance = get_exchange_rate_service()

    # Assert
    assert service_instance is not None
    assert isinstance(service_instance, ExchangeRateService)
def test_get_exchange_rates_success(mocker):
    """
    Test a successful request to fetch exchange rates.
    """
    # Arrange
    currency = "USD"
    mock_response_data = {
        "base": "USD",
        "rates": {"EUR": 0.85, "GBP": 0.75}
    }
    
    # FIX: Patch where it is imported inside the ROUTER file to avoid module lookup bugs
    mock_service = mocker.patch(
        'services.exchange_rate_service.ExchangeRateService.get_exchange_rates', 
        return_value=mock_response_data
    )

    # Act
    response = client.get(f"/v1/exchange/rates/{currency}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_response_data
    mock_service.assert_called_once_with(currency)


def test_get_exchange_rates_not_found(mocker):
    """
    Test the endpoint behavior when the service returns an error or failure response.
    """
    # Arrange
    currency = "INVALID"
    mock_error_data = {"error": "Currency symbol not supported"}
    
    # FIX: Patch where it is imported inside the ROUTER file
    mock_service = mocker.patch(
        'services.exchange_rate_service.ExchangeRateService.get_exchange_rates', 
        return_value=mock_error_data
    )

    # Act
    response = client.get(f"/v1/exchange/rates/{currency}")

    # Assert
    assert response.json() == mock_error_data
    mock_service.assert_called_once_with(currency)


def test_get_exchange_rates_unauthenticated():
    """
    Test that the route fails if the user authentication fails.
    """
    # Arrange: Remove the successful auth override and simulate an auth error
    def mock_authenticate_fail():
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    app.dependency_overrides[authenticate] = mock_authenticate_fail

    # Act
    response = client.get("/v1/exchange/rates/USD")

    # Assert
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid credentials"