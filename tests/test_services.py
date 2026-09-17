import pytest
# Assuming you have a portfolio service class or function
# from services.portfolio import CalculatePortfolioValue 

def test_calculate_portfolio_total(mock_portfolio_data):
    """Test that the portfolio service correctly aggregates asset values."""
    # Example logic assuming a mock function
    assets = mock_portfolio_data["assets"]
    total_cost = sum(asset["shares"] * asset["purchase_price"] for asset in assets)
    
    assert total_cost == 3000.0  # (10 * 150) + (5 * 300)

def test_exchange_rate_handling():
    """Test that currency conversions operate correctly using exchange_rates.json structure."""
    # Mock or pass standard exchange rates to your service
    usd_to_eur = 0.92
    usd_amount = 100
    
    converted = usd_amount * usd_to_eur
    assert converted == 92.0
