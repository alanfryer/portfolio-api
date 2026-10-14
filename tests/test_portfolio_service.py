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
class DummyStocksResponse:
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
#        try:
#            portfolio_service.get_latest_price("AAPL", "user_portfolio_123")
#        except Exception as e:
            # Add assertions here once you decide if it raises a specific exception
#            pass
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            portfolio_service.get_latest_price("AAPL", "user_portfolio_123")

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "No pricing information returned for asset symbol" in exc_info.value.detail

def test_get_portfolio_valuation_success(portfolio_service, mock_db_service):
    """Test standard evaluation across a mix of multiple stable stock entries."""
    # 1. Mock DB returning two active positions
    mock_db_service.get_stocks.return_value = [
        {"symbol": "AAPL"},
        {"symbol": "MSFT"}
    ]

    # 2. Mock specific StockResponse data models returned by get_latest_price
    stock_1 = DummyStockResponse(symbol="AAPL", daily_change=10.50, overall_change=150.00)
    stock_2 = DummyStockResponse(symbol="MSFT", daily_change=-5.25, overall_change=50.00)

    # 3. Patch get_latest_price and StocksResponse mapping
    with patch.object(portfolio_service, 'get_latest_price') as mock_latest_price, \
         patch('services.portfolio_service.StocksResponse', side_effect=DummyStocksResponse):
        
        # Side effect maps specific response values per symbol requested
        mock_latest_price.side_effect = lambda symbol, pid: stock_1 if symbol == "AAPL" else stock_2

        # Act
        result = portfolio_service.get_portfolio_valuation("user_portfolio_123")

        # Assert calculations: 
        # portfolio_daily_position = 10.50 + (-5.25) = 5.25
        # portfolio_position = 150.00 + 50.00 = 200.00
        assert result is not None
        assert result.portfolio_daily_position == 5.25
        assert result.portfolio_position == 200.00
        assert len(result.stocks) == 2


def test_get_portfolio_valuation_empty_db(portfolio_service, mock_db_service):
    """Test that an unconfigured or empty portfolio explicitly returns None."""
    # Arrange
    mock_db_service.get_stocks.return_value = []

    # Act
    result = portfolio_service.get_portfolio_valuation("user_portfolio_empty")

    # Assert
    assert result is None


def test_get_portfolio_valuation_fault_containment_and_skips(portfolio_service, mock_db_service):
    """Test loop fault containment skips error-prone assets safely."""
    # 1. Mock DB returning three assets (one missing symbol, one throwing HTTP 404, one successful)
    mock_db_service.get_stocks.return_value = [
        {"symbol": None},  # Skipped via empty key validation
        {"symbol": "INVALID"},  # Will throw an API exception
        {"symbol": "GOOG"}  # Valid target asset
    ]

    valid_stock = DummyStockResponse(symbol="GOOG", daily_change=25.00, overall_change=300.00)

    # 2. Configure mock actions for different symbols
    with patch.object(portfolio_service, 'get_latest_price') as mock_latest_price, \
         patch('services.portfolio_service.StocksResponse', side_effect=DummyStocksResponse):
        
        def dynamic_latest_price(symbol, portfolio_id):
            if symbol == "INVALID":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="No pricing information found"
                )
            return valid_stock

        mock_latest_price.side_effect = dynamic_latest_price

        # Act
        result = portfolio_service.get_portfolio_valuation("user_portfolio_123")

        # Assert: Loop continues instead of crashing out. Total calculations exclude "INVALID"
        assert result is not None
        assert result.portfolio_daily_position == 25.00
        assert result.portfolio_position == 300.00
        assert len(result.stocks) == 1
        assert result.stocks[0].symbol == "GOOG"


def test_get_portfolio_valuation_unhandled_exception_bypass(portfolio_service, mock_db_service):
    """Test that standard base Exception crashes are safely caught and bypassed inside loop."""
    mock_db_service.get_stocks.return_value = [
        {"symbol": "CRASH"},
        {"symbol": "AMZN"}
    ]

    valid_stock = DummyStockResponse(symbol="AMZN", daily_change=5.00, overall_change=20.00)

    with patch.object(portfolio_service, 'get_latest_price') as mock_latest_price, \
         patch('services.portfolio_service.StocksResponse', side_effect=DummyStocksResponse):
        
        def dynamic_latest_price(symbol, portfolio_id):
            if symbol == "CRASH":
                raise Exception("Fatal internal calculation mismatch error")
            return valid_stock

        mock_latest_price.side_effect = dynamic_latest_price

        # Act
        result = portfolio_service.get_portfolio_valuation("user_portfolio_123")

        # Assert: General exception was contained by the second try-except block
        assert result is not None
        assert result.portfolio_daily_position == 5.00
        assert len(result.stocks) == 1