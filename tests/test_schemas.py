import pytest
from pydantic import ValidationError, SecretStr
from schemas import (  # Replace with your actual module name
    User,
    Stock,
    StockResponse,
    StocksResponse,
    StockUpdateInput,
    UserUpdateInput,
    Portfolio,
    Portfolios,
    validate_list_scopes,
)

# =====================================================================
# 1. Tests for validate_list_scopes & AnyScopeList
# =====================================================================

def test_validate_list_scopes_valid_list():
    """Validates that a standard list of allowed scopes is returned correctly."""
    assert validate_list_scopes(["admin", "view"]) == ["admin", "view"]

def test_validate_list_scopes_comma_string():
    """Validates that a comma-separated string is properly parsed and stripped."""
    assert validate_list_scopes("admin, view, add ") == ["admin", "view", "add"]

def test_validate_list_scopes_invalid_type():
    """Ensures a ValueError is raised when providing unsupported types (e.g., dict)."""
    with pytest.raises(ValueError, match="Input must be a list or a comma-separated string"):
        validate_list_scopes({"admin": True})

def test_validate_list_scopes_invalid_items():
    """Ensures custom validation catches unapproved strings/scopes."""
    # Add the 'r' prefix here to make it a raw string:
    with pytest.raises(ValueError, match=r"Invalid scope\(s\) found: root, superuser"):
        validate_list_scopes(["admin", "root", "superuser"])



# =====================================================================
# 2. Tests for User Schema
# =====================================================================

def test_user_creation_success():
    """Validates successful schema instantiations for a User with clean values."""
    user = User(
        username="test@example.com",
        password=SecretStr("supersecret123"),
        scopes="admin,view"
    )
    assert user.username == "test@example.com"
    assert user.password.get_secret_value() == "supersecret123"
    assert user.scopes == ["admin", "view"]

def test_user_creation_invalid_email():
    """Ensures Pydantic's EmailStr triggers on malformed email addresses."""
    with pytest.raises(ValidationError):
        User(username="notanemail", password=SecretStr("pass"), scopes=["view"])


# =====================================================================
# 3. Tests for Stock, StockResponse & StocksResponse
# =====================================================================

@pytest.fixture
def base_stock_data():
    return {
        "symbol": "AAPL",
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "owned": 10.5,
        "cost": 150.0,
        "portfolio_id": "port_abc123"
    }

def test_stock_creation_success(base_stock_data):
    """Validates full parsing of properties matching the Stock schema."""
    stock = Stock(**base_stock_data)
    assert stock.symbol == "AAPL"
    assert stock.portfolio_id == "port_abc123"

def test_stock_response_success(base_stock_data):
    """Validates nested generation of historical / calculated position data."""
    response_data = {
        **base_stock_data,
        "date": "2026-11-02",
        "open_price": 170.0,
        "close_price": 175.5,
        "close_value": 1842.75,
        "daily_change": 5.5,
        "overall_change": 25.5
    }
    stock_resp = StockResponse(**response_data)
    assert stock_resp.close_value == 1842.75
    assert stock_resp.symbol == "AAPL"

def test_stocks_response_empty_list():
    """Verifies standard composite responses handle layout totals alongside zeroed entries."""
    response = StocksResponse(
        portfolio_daily_position=120.50,
        portfolio_position=5400.00,
        stocks=[]
    )
    assert response.stocks == []


# =====================================================================
# 4. Tests for Input Modifiers (StockUpdateInput, UserUpdateInput)
# =====================================================================

def test_stock_update_input_partial():
    """Ensures partial updates accept subsets of attributes while keeping defaults None."""
    update = StockUpdateInput(company="New Tech Corp")
    assert update.company == "New Tech Corp"
    assert update.owned is None

@pytest.mark.parametrize("owned, cost", [(-5.0, 10.0), (10.0, -1.0), (0.0, 10.0)])
def test_stock_update_input_constraints(owned, cost):
    """Enforces Field constraints: owned must be > 0, cost must be >= 0."""
    with pytest.raises(ValidationError):
        StockUpdateInput(owned=owned, cost=cost)

def test_user_update_input():
    """Confirms payload structures safely evaluate incoming SecretStr values."""
    update = UserUpdateInput(password=SecretStr("newpass"))
    assert update.password.get_secret_value() == "newpass"


# =====================================================================
# 5. Tests for Portfolio & Portfolios
# =====================================================================

def test_portfolios_list_parsing():
    """Confirms wrapper list objects map structural arrays natively."""
    data = {
        "portfolios": [
            {"id": "p1", "name": "Growth", "username": "user1@test.com"},
            {"id": "p2", "name": "Dividends", "username": "user1@test.com"}
        ]
    }
    result = Portfolios(**data)
    assert len(result.portfolios) == 2
    assert result.portfolios[0].name == "Growth"
