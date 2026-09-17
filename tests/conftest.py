import pytest
from fastapi.testclient import TestClient
from main import app  # Adjust this import based on your exact main.py layout

@pytest.fixture
def client():
    """Provides a clean FastAPI TestClient for integration tests."""
    with TestClient(app) as client:
        yield client

@pytest.fixture
def mock_portfolio_data():
    """Sample mock data mimicking the expected structure of portfolio.json."""
    return {
        "assets": [
            {"ticker": "AAPL", "shares": 10, "purchase_price": 150.0},
            {"ticker": "MSFT", "shares": 5, "purchase_price": 300.0}
        ]
    }
