import pytest
from fastapi.testclient import TestClient
from fastapi import APIRouter, FastAPI, status

# Corrected imports matching your layout
from routers.exchange_rates import router, get_exchange_rate_service
from services.authorization_service import authenticate
from services.exchange_rate_service import ExchangeRateService

# -------------------------------------------------------------------------
# Reusable Fixtures & Lifecycle Control
# -------------------------------------------------------------------------

@pytest.fixture
def app_instance():
    """Generates an isolated FastAPI instance specifically for this test module execution."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def setup_dependencies(app_instance):
    """Overrides the authentication dependency context to simulate a logged-in user."""
    def mock_authenticate():
        return {"username": "test_user"}
        
    app_instance.dependency_overrides[authenticate] = mock_authenticate
    yield
    # Clean up overrides after the test finishes to avoid test leakage
    app_instance.dependency_overrides.clear()


@pytest.fixture
def client(app_instance):
    """
    Provides a managed TestClient. Using a context manager inside a yield block
    ensures all resources opened during test executions are safely closed.
    """
    with TestClient(app_instance) as test_client:
        yield test_client

# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------

def test_router_initialization():
    """Test that the APIRouter instance is initialized correctly."""
    assert isinstance(router, APIRouter)


def test_get_exchange_rate_service_provider():
    """Test that the dependency injection factory function instantiates a valid service."""
    service_instance = get_exchange_rate_service()
    assert service_instance is not None
    assert isinstance(service_instance, ExchangeRateService)


def test_get_exchange_rates_success(mocker, client):
    """Test a successful request to fetch exchange rates."""
    # Arrange
    currency = "USD"
    mock_response_data = {
        "base": "USD",
        "rates": {"EUR": 0.85, "GBP": 0.75}
    }
    
    # Patch where it is imported inside the service file
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


def test_get_exchange_rates_not_found(mocker, client):
    """Test the endpoint behavior when the service returns an error response."""
    # Arrange
    currency = "INVALID"
    mock_error_data = {"error": "Currency symbol not supported"}
    
    mock_service = mocker.patch(
        'services.exchange_rate_service.ExchangeRateService.get_exchange_rates', 
        return_value=mock_error_data
    )

    # Act
    response = client.get(f"/v1/exchange/rates/{currency}")

    # Assert
    assert response.json() == mock_error_data
    mock_service.assert_called_once_with(currency)


def test_get_exchange_rates_unauthenticated(app_instance, client):
    """Test that the route fails if the user authentication fails."""
    # Arrange: Override with a failing auth configuration
    def mock_authenticate_fail():
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    app_instance.dependency_overrides[authenticate] = mock_authenticate_fail

    # Act
    response = client.get("/v1/exchange/rates/USD")

    # Assert
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid credentials"