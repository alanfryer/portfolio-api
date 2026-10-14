import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from fastapi.exceptions import HTTPException

# Using your specific router filename inside the routers package directory
from routers.portfolio import router, get_db_service, get_portfolio_service
from services.authorization_service import authorize, authenticate
from schemas import Portfolio, Portfolios, Stock, StockResponse

# Setup test application
app = FastAPI()
app.include_router(router)
client = TestClient(app)

@pytest.fixture
def mock_db():
    mock = MagicMock()
    app.dependency_overrides[get_db_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_db_service, None)

@pytest.fixture
def mock_portfolio_service():
    mock = MagicMock()
    app.dependency_overrides[get_portfolio_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_portfolio_service, None)

@pytest.fixture(autouse=True)
def mock_auth():
    # Automatically bypass authorization and authentication rules globally for testing
    app.dependency_overrides[authorize] = lambda: {"user_id": "test_user"}
    app.dependency_overrides[authenticate] = lambda: {"user_id": "test_user"}
    yield
    app.dependency_overrides.pop(authorize, None)
    app.dependency_overrides.pop(authenticate, None)


# --- HELPERS FOR VALID SCHEMAS ---

def get_valid_portfolio_dict(portfolio_id="p1"):
    return {
        "id": portfolio_id,
        "name": "Tech Growth",
        "username": "alanfryer@example.com"  # Must satisfy EmailStr validation
    }

def get_valid_stock_dict(symbol="AAPL", portfolio_id="p1"):
    return {
        "symbol": symbol,
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "owned": 10.0,
        "cost": 1500.0,
        "portfolio_id": portfolio_id
    }

def get_valid_stock_response_dict(symbol="AAPL", portfolio_id="p1"):
    stock_base = get_valid_stock_dict(symbol, portfolio_id)
    # Append the extra metrics fields required by StockResponse schema
    stock_base.update({
        "date": "2026-10-10",
        "open_price": 150.0,
        "close_price": 155.0,
        "close_value": 1550.0,
        "daily_change": 5.0,
        "overall_change": 50.0
    })
    return stock_base


# --- PORTFOLIO TESTS ---

def test_get_portfolios(mock_db):
    # Returns structural Pydantic mapping matching Portfolios schema model structure
    mock_db.get_portfolios.return_value = Portfolios(portfolios=[
        Portfolio(**get_valid_portfolio_dict("p1"))
    ])
    response = client.get("/v1/portfolios/")
    assert response.status_code == status.HTTP_200_OK
    mock_db.get_portfolios.assert_called_once()

def test_get_portfolio_success(mock_db):
    mock_db.get_portfolio.return_value = Portfolio(**get_valid_portfolio_dict("p1"))
    response = client.get("/v1/portfolios/p1")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == "p1"

def test_add_portfolio_success(mock_db):
    mock_db.get_portfolio.return_value = None
    payload = get_valid_portfolio_dict("p1")
    response = client.post("/v1/portfolios/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    mock_db.add_portfolio.assert_called_once()

def test_add_portfolio_conflict(mock_db):
    mock_db.get_portfolio.return_value = Portfolio(**get_valid_portfolio_dict("p1"))
    payload = get_valid_portfolio_dict("p1")
    response = client.post("/v1/portfolios/", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT

def test_delete_portfolio_success(mock_db):
    mock_db.get_portfolio.return_value = Portfolio(**get_valid_portfolio_dict("p1"))
    response = client.delete("/v1/portfolios/p1")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_db.delete_portfolio.assert_called_once_with("p1")

def test_delete_portfolio_not_found(mock_db):
    mock_db.get_portfolio.return_value = None
    response = client.delete("/v1/portfolios/p1")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- STOCKS TESTS ---

def test_get_stocks_list_without_valuation(mock_db):
    mock_db.get_stocks.return_value = [Stock(**get_valid_stock_dict("AAPL", "p1"))]
    response = client.get("/v1/portfolios/p1/stocks")
    assert response.status_code == status.HTTP_200_OK
    mock_db.get_stocks.assert_called_once_with("p1")

def test_get_portfolio_valuation_success(mock_db, mock_portfolio_service):
    # This route returns StocksResponse or list[Stock] / list[StockResponse]
    # We populate the required metrics fields to completely satisfy StockResponse specifications
    mock_portfolio_service.get_portfolio_valuation.return_value = [
        StockResponse(**get_valid_stock_response_dict("AAPL", "p1"))
    ]
    response = client.get("/v1/portfolios/p1/stocks?view=valuation")
    assert response.status_code == status.HTTP_200_OK

def test_get_portfolio_valuation_not_found(mock_db, mock_portfolio_service):
    mock_portfolio_service.get_portfolio_valuation.return_value = None
    response = client.get("/v1/portfolios/p1/stocks?view=valuation")
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_get_portfolio_valuation_bad_gateway(mock_db, mock_portfolio_service):
    mock_portfolio_service.get_portfolio_valuation.side_effect = Exception("Valuation API failed")
    response = client.get("/v1/portfolios/p1/stocks?view=valuation")
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# --- INDIVIDUAL STOCK ROUTE TESTS ---

def test_get_single_stock_success(mock_db):
    mock_db.get_stock.return_value = Stock(**get_valid_stock_dict("AAPL", "p1"))
    response = client.get("/v1/portfolios/p1/stocks/aapl")
    assert response.status_code == status.HTTP_200_OK
    mock_db.get_stock.assert_called_once_with("AAPL", "p1")

def test_get_single_stock_not_found(mock_db):
    mock_db.get_stock.return_value = None
    response = client.get("/v1/portfolios/p1/stocks/aapl1")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    mock_db.get_stock.assert_called_once_with("AAPL1", "p1")    

def test_get_single_stock_valuation_success(mock_db, mock_portfolio_service):
    mock_portfolio_service.get_latest_price.return_value = StockResponse(**get_valid_stock_response_dict("AAPL", "p1"))
    response = client.get("/v1/portfolios/p1/stocks/aapl?view=valuation")
    assert response.status_code == status.HTTP_200_OK
    mock_portfolio_service.get_latest_price.assert_called_once_with("AAPL", "p1")

def test_get_single_stock_valuation_http_error(mock_db, mock_portfolio_service):
    mock_portfolio_service.get_latest_price.side_effect = HTTPException(status_code=400, detail="Error")
    response = client.get("/v1/portfolios/p1/stocks/aapl?view=valuation")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_get_stock_valuation_price_missing(mock_portfolio_service):

    # Arrange
    mock_portfolio_service.get_latest_price.return_value = None

    # Act
    response = client.get("v1/portfolios/p1/stocks/tsla?view=valuation")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Real-time pricing unavailable" in response.json()["detail"]
    
def test_add_stock_to_portfolio_success(mock_db):
    mock_db.get_stock.return_value = None
    payload = get_valid_stock_dict("TSLA", "p1")
    response = client.post("/v1/portfolios/p1/stocks", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    mock_db.add_stock.assert_called_once()

def test_add_stock_to_portfolio_conflict(mock_db):
    mock_db.get_stock.return_value = Stock(**get_valid_stock_dict("TSLA", "p1"))
    payload = get_valid_stock_dict("TSLA", "p1")
    response = client.post("/v1/portfolios/p1/stocks", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT

def test_update_portfolio_stock_success(mock_db):
    mock_db.get_stock.return_value = Stock(**get_valid_stock_dict("AAPL", "p1"))
    payload = {"owned": 15.0, "cost": 1550.0}  # Matches valid attributes inside StockUpdateInput
    response = client.put("/v1/portfolios/p1/stocks/aapl", json=payload)
    assert response.status_code == status.HTTP_200_OK
    mock_db.update_stock.assert_called_once()

def test_update_portfolio_stock_not_found(mock_db):
    mock_db.get_stock.return_value = None
    payload = {"owned": 15.0, "cost": 1550.0}
    response = client.put("/v1/portfolios/p1/stocks/aapl", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_delete_portfolio_stock_success(mock_db):
    mock_db.get_stock.return_value = Stock(**get_valid_stock_dict("AAPL", "p1"))
    response = client.delete("/v1/portfolios/p1/stocks/aapl")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_db.delete_stock.assert_called_once_with("AAPL", "p1")
    
def test_delete_portfolio_stock_not_found(mock_db):
    mock_db.get_stock.return_value = None
    response = client.delete("/v1/portfolios/p1/stocks/aapl")
    assert response.status_code == status.HTTP_404_NOT_FOUND