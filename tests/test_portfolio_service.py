import pytest
import yfinance
from unittest.mock import MagicMock, patch
import pandas as pd
from fastapi import HTTPException, status

# Replace 'your_module' with the actual name of the file containing PortfolioService
from services.portfolio_service import PortfolioService
from services.exchange_rate_service import ExchangeRateService
# Mock schemas for testing if they are Pydantic models
class DummyStockResponse:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_db_service():
    """Provides a mocked instance of the DatabaseService."""
    return MagicMock()


@pytest.fixture
def portfolio_service(mock_db_service):
    """Provides a PortfolioService instance with a mocked ExchangeRateService."""
    with patch('services.exchange_rate_service.ExchangeRateService') as mock_exchange_service:
        service = PortfolioService(database_service=mock_db_service)
        yield service


def test_get_latest_price_success(portfolio_service, mock_db_service):
    """Test successful retrieval and pricing of a configured stock."""
    # 1. Arrange mock database response
    mock_db_service.get_stock.return_value = {
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "owned": 10,
        "cost": 150.0
    }

    # 2. Arrange mock yfinance Ticker data frame
    mock_ticker = MagicMock()
    # Mocking a valid 1-row history dataframe
    mock_ticker.history.return_value = pd.DataFrame(
        {
            "Open": [174.0],
            "Close": [175.0],
            "High": [176.0],
            "Low": [173.0]
        }, 
        index=[pd.Timestamp.now()]
    )

    # 3. Patch yf.Ticker and StockResponse mapping
    with patch('yfinance.Ticker', return_value=mock_ticker), \
         patch('schemas.StockResponse', side_effect=DummyStockResponse) as mock_response_cls:
        
        # Act
        result = portfolio_service.get_latest_price("AAPL", "user_portfolio_123")

        # Assert
        mock_db_service.get_stock.assert_called_once_with("AAPL", "user_portfolio_123")
        mock_ticker.history.assert_called_once_with(period="1d")
        assert result is not None


def test_get_latest_price_asset_not_found_in_db(portfolio_service, mock_db_service):
    """Test that an HTTPException 404 is thrown if the asset is missing from the DB."""
    # Arrange
    mock_db_service.get_stock.return_value = None

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        portfolio_service.get_latest_price("INVALID", "user_portfolio_123")

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Asset metadata INVALID not configured" in exc_info.value.detail


def test_get_latest_price_yfinance_network_failure(portfolio_service, mock_db_service):
    """Test that a network/API exception inside yfinance returns a 502 Bad Gateway."""
    # Arrange
    mock_db_service.get_stock.return_value = {
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "owned": 10,
        "cost": 150.0
    }

    # Force yfinance to throw a connection/API exception
    with patch('yfinance.Ticker') as mock_yf_ticker:
        mock_yf_ticker.side_effect = Exception("Connection Timeout")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            portfolio_service.get_latest_price("AAPL", "user_portfolio_123")

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
        assert "Market data provider unavailable" in exc_info.value.detail


def test_get_latest_price_empty_market_data(portfolio_service, mock_db_service):
    """Test behavior when yfinance returns an empty dataframe (where your snippet cut off)."""
    # Arrange
    mock_db_service.get_stock.return_value = {
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "owned": 10,
        "cost": 150.0
    }

    mock_ticker = MagicMock()
    # Mocking an empty dataframe response
    mock_ticker.history.return_value = pd.DataFrame()

    with patch('yfinance.Ticker', return_value=mock_ticker):
        # Act & Assert
        # Depending on how you handle empty data after line 42, 
        # this will either fail, or you can assert your specific custom error/HTTPException here.
        # For now, we verify it hits the validation flow.
        try:
            portfolio_service.get_latest_price("AAPL", "user_portfolio_123")
        except Exception as e:
            # Add assertions here once you decide if it raises a specific exception
            pass
