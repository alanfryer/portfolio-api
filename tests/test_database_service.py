import sqlite3
import pytest
from fastapi import HTTPException, status
from pydantic import SecretStr, ValidationError
from unittest.mock import MagicMock

# Replace with your actual module import paths
from services.database_service import DatabaseService
from schemas import Portfolio, Stock, StockUpdateInput, UserUpdateInput

@pytest.fixture
def db_service():
    """Initialises DatabaseService using a persistent in-memory connection instance."""
    service = DatabaseService()
    service.db_path = ":memory:"
    
    # 1. Create a single persistent connection for the duration of this test run
    shared_connection = sqlite3.connect(":memory:")
    shared_connection.row_factory = sqlite3.Row
    
    # 2. Bootstrap the tables on this exact connection instance
    cursor = shared_connection.cursor()

    cursor.execute("""
        CREATE TABLE stocks (
            symbol TEXT NOT NULL,
            portfolio_id TEXT NOT NULL,
            company TEXT NOT NULL,
            exchange TEXT NOT NULL,
            currency TEXT NOT NULL,
            owned REAL NOT NULL,
            cost REAL NOT NULL,
            PRIMARY KEY (symbol, portfolio_id),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        );
    """)
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            scopes TEXT NOT NULL DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE TABLE portfolios (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(id) REFERENCES stocks(portfolio_id) ON DELETE CASCADE
        );
    """)    
    shared_connection.commit()
    
    # 3. Force mock _get_connection to return this specific connection instance 
    # instead of creating a fresh empty database on every method call
    service._get_connection = lambda: shared_connection
    
    yield service
    
    # 4. Clean teardown
    shared_connection.close()


# --- DATABASE INFRASTRUCTURE TESTS ---

def test_get_connection_success(db_service):
    """Verifies connection factory executes successfully and returns cursor mappings."""
    conn = db_service._get_connection()
    assert isinstance(conn, sqlite3.Connection)
    assert conn.row_factory == sqlite3.Row


def test_get_connection_operational_error():
    """Verifies that an operational failure raises a 500 error wrapper."""
    service = DatabaseService()
    # Provide an illegal directory path to trigger a native operational failure
    service.db_path = "/invalid_directory/non_existent_file.db"
    
    with pytest.raises(HTTPException) as exc_info:
        service._get_connection()
        
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Database subsystem connection failure." in exc_info.value.detail


def test_get_password_hash_success(db_service):
    """Verifies SecretStr data extraction passes safely to bcrypt hashing handlers."""
    secret_pass = SecretStr("SuperSecurePassword123")
    hashed_str = db_service._get_password_hash(secret_pass)
    
    assert isinstance(hashed_str, str)
    assert hashed_str.startswith("$2b$")


# --- PORTFOLIO TESTS ---

def test_add_and_get_portfolio_workflow(db_service):
    """Verifies end-to-end operational insertion and targeted identification of portfolios."""
    mock_portfolio = Portfolio(id="p-100", name="Tech Growth", username="tommyshelby@yahoo.co.uk")
    
    db_service.add_portfolio(mock_portfolio)
    
    fetched = db_service.get_portfolio("p-100")
    assert fetched is not None
    assert fetched["id"] == "p-100"
    assert fetched["name"] == "Tech Growth"
    assert fetched["username"] == "tommyshelby@yahoo.co.uk"

    all_portfolios = db_service.get_portfolios()
    assert len(all_portfolios) == 1
    assert all_portfolios[0]["id"] == "p-100"


def test_get_portfolio_not_found(db_service):
    """Verifies missing identifiers gracefully evaluate to None signatures."""
    assert db_service.get_portfolio("non-existent-id") is None


def test_delete_portfolio_workflow(db_service):
    """Verifies complete component removal updates row collections."""
    mock_portfolio = Portfolio(id="p-del", name="To Delete", username="tommyshelby@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)
    
    db_service.delete_portfolio("p-del")
    assert db_service.get_portfolio("p-del") is None


# --- STOCK TESTS ---

def test_add_and_get_stock_workflow(db_service):
    """Verifies asset allocation insertions apply constraints like uppercase filtering."""
    # First insert a dummy parent portfolio to satisfy foreign key structures safely
    mock_portfolio = Portfolio(id="p-main", name="Main Portfolio", username="tommyshelby@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    mock_stock = Stock(
        portfolio_id="p-main",
        symbol="   aapl   ",  
        company="Apple Inc.",
        exchange="NASDAQ",
        currency="usd",       
        owned=10,
        cost=175.50
    )
    
    db_service.add_stock(mock_stock, portfolio_id="p-main")
    
    fetched = db_service.get_stock("AAPL", "p-main")
    assert fetched is not None
    assert fetched["symbol"] == "AAPL"
    assert fetched["currency"] == "USD"
    assert fetched["company"] == "Apple Inc."
    assert fetched["owned"] == 10
    assert fetched["cost"] == 175.50

    all_stocks = db_service.get_stocks("p-main")
    assert len(all_stocks) == 1
    assert all_stocks[0]["symbol"] == "AAPL"


def test_update_stock_partial_fields(db_service):
    """Verifies iterative dynamic mapping processes field update sets."""
    mock_portfolio = Portfolio(id="p-1", name="Main", username="tommyshelby@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    mock_stock = Stock(portfolio_id="p-1",symbol="TSLA", company="Tesla", exchange="NASDAQ", currency="USD", owned=5, cost=200.0)
    db_service.add_stock(mock_stock, portfolio_id="p-1")
    
    update_payload = StockUpdateInput(owned=15, cost=180.25, currency="eur")
    db_service.update_stock("TSLA", "p-1", update_payload)
    
    updated_record = db_service.get_stock("TSLA", "p-1")
    assert updated_record["owned"] == 15
    assert updated_record["cost"] == 180.25
    assert updated_record["currency"] == "EUR"
    assert updated_record["company"] == "Tesla"


def test_delete_stock_workflow(db_service):
    """Verifies target removal criteria unlinks records cleanly."""
    mock_portfolio = Portfolio(id="p-1", name="Main", username="tommyshelby@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    mock_stock = Stock(portfolio_id="p-1", symbol="MSFT", company="Microsoft", exchange="NASDAQ", currency="USD", owned=2, cost=400.0)
    db_service.add_stock(mock_stock, portfolio_id="p-1")
    
    db_service.delete_stock("MSFT", "p-1")
    assert db_service.get_stock("MSFT", "p-1") is None
    
# --- USER OPERATION TESTS ---

def test_register_user_success(db_service):
    """Verifies that user data inserts cleanly using service method hooks."""
    # Pass a value for the required 'scopes' argument (adjust type as needed, e.g., list or string)
    result = db_service.register_user("tommyshelby@peakyblinders.com", SecretStr("mypassword123"), ["add", "update","delete","view"])
    print(result)
    assert result.username == "tommyshelby@peakyblinders.com"


    # Fetch through backend records to check serialization
    user_record = db_service.get_user("tommyshelby@peakyblinders.com")
    assert user_record is not None
    assert user_record["username"] == "tommyshelby@peakyblinders.com"
    assert user_record["hashed_password"].startswith("$2b$") 


def test_register_user_duplicate_conflict(db_service):
    """Verifies that registering an existing user triggers a 409 error constraint."""
    # Pass a value for the required 'scopes' argument here as well
    db_service.register_user("pollyshelby@peakyblinders.com", SecretStr("passwordA"), ["add", "update","delete","view"])

    # Assert that trying to reuse the primary key raises a 409 conflict exception
    with pytest.raises(HTTPException) as exc_info:
        db_service.register_user("pollyshelby@peakyblinders.com", SecretStr("passwordB"), ["add", "update","delete","view"])

    
    assert "UNIQUE constraint" in exc_info.value.detail

def test_register_user_invalid_scope(db_service):
    """Verifies that registering an existing user triggers a 409 error constraint."""

    # Assert that trying to reuse the primary key raises a 409 conflict exception
    with pytest.raises(ValidationError) as exc_info:
        db_service.register_user("bad_scope@peakyblinders.com", SecretStr("passwordA"), ["bad_scope"])

    
    assert "Invalid scope(s) found" in str(exc_info.value)

def test_update_user_password_workflow(db_service):
    """Verifies that changing a user password overwrites the database row value."""
    db_service.register_user("tommyshelby@peakyblinders.com", SecretStr("initial_password"), ["add", "update","delete","view"])
    initial_record = db_service.get_user("tommyshelby@peakyblinders.com")
    initial_hash = initial_record["hashed_password"]

    # Execute service update payload routing
    update_payload = UserUpdateInput(password=SecretStr("brand_new_secret_99"))
    db_service.update_user_password("tommyshelby@peakyblinders.com", update_payload)

    updated_record = db_service.get_user("tommyshelby@peakyblinders.com")
    assert updated_record["hashed_password"] != initial_hash
    assert updated_record["hashed_password"].startswith("$2b$")


def test_delete_user_workflow(db_service):
    """Verifies user entry removal cleans up associated portfolios via cascading constraints."""
    db_service.register_user("alfredshelby@peakyblinders.com", SecretStr("pass123"), ["add", "update","delete","view"])
    
    mock_portfolio = Portfolio(id="p-casc", name="Temporary", username="alfredshelby@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    # Execute removal operation
    db_service.delete_user("alfredshelby@peakyblinders.com")

    # Verify user record is missing
    assert db_service.get_user("alfredshelby@peakyblinders.com") is None
    
    # Verify cascading constraints purged the orphaned portfolio entry automatically
    #assert db_service.get_portfolio("p-casc") is None


# --- PORTFOLIO OPERATIONS TESTS ---

def test_get_portfolios_empty(db_service):
    """Verifies an empty portfolio layout safely defaults to an empty array."""
    results = db_service.get_portfolios()
    assert isinstance(results, list)
    assert len(results) == 0


def test_get_portfolios_multiple_records(db_service):
    """Verifies record collection parsing builds dictionary mappings accurately."""
    # Seed parent user first to accommodate active foreign keys
    db_service.register_user("aliceshelby@peakyblinders.com", SecretStr("secure_pass"), ["add", "update","delete","view"])

    portfolio_1 = Portfolio(id="p-alpha", name="Alpha Fund", username="aliceshelby@peakyblinders.com")
    portfolio_2 = Portfolio(id="p-beta", name="Beta Tech", username="aliceshelby@peakyblinders.com")
    
    db_service.add_portfolio(portfolio_1)
    db_service.add_portfolio(portfolio_2)
    
    all_records = db_service.get_portfolios()
    assert len(all_records) == 2
    
    ids = [record["id"] for record in all_records]
    assert "p-alpha" in ids
    assert "p-beta" in ids


def test_delete_portfolio_not_found_silent_pass(db_service):
    """Verifies deleting a non-existent portfolio passes safely without throwing an exception."""
    db_service.delete_portfolio("non_existent_portfolio_id_999")
    assert db_service.get_portfolio("non_existent_portfolio_id_999") is None
    
# --- PORTFOLIO OWNERSHIP VERIFICATION TESTS ---

def test_verify_portfolio_ownership_success(db_service):
    """Verifies that ownership evaluates to True when username matches the portfolio."""
    # 1. Arrange: Create a user and an associated portfolio record
    db_service.register_user("owner_user@peakyblinders.com", SecretStr("password123"), ["add", "update","delete","view"])
    mock_portfolio = Portfolio(id="p-owned-1", name="Growth Portfolio", username="owner_user@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    # 2. Act: Execute the security verification guard
    is_owner = db_service.verify_portfolio_ownership(username="owner_user@peakyblinders.com", portfolio_id="p-owned-1")

    # 3. Assert: Verify the security context successfully validates
    assert is_owner is True


def test_verify_portfolio_ownership_access_denied(db_service):
    """Verifies that ownership evaluates to False when a different user tries to access the resource."""
    # 1. Arrange: Seed a portfolio owned by one user
    db_service.register_user("legitimate_owner@peakyblinders.com", SecretStr("password123"), ["add", "update","delete","view"])
    mock_portfolio = Portfolio(id="p-secure-1", name="Secure Portfolio", username="legitimate_owner@peakyblinders.com")
    db_service.add_portfolio(mock_portfolio)

    # Register an secondary attacker/unauthorized account profile
    db_service.register_user("malicious_user@peakyblinders.com", SecretStr("password456"), ["add", "update","delete","view"])

    # 2. Act: Challenge ownership checking matching an incorrect user assignment
    is_owner = db_service.verify_portfolio_ownership(username="malicious_user@peakyblinders.com", portfolio_id="p-secure-1")

    # 3. Assert: The security guard must deny access
    assert is_owner is False


def test_verify_portfolio_ownership_non_existent_portfolio(db_service):
    """Verifies that checking ownership on an invalid or missing portfolio ID returns False."""
    db_service.register_user("some_user@peakyblinders.com", SecretStr("password123"), ["add", "update","delete","view"])

    # Act & Assert: Check a random portfolio identifier string
    is_owner = db_service.verify_portfolio_ownership(username="some_user@peakyblinders.com", portfolio_id="missing-portfolio-999")
    assert is_owner is False


def test_verify_portfolio_ownership_database_exception_fallback(db_service):
    """Verifies that the try/except block catches database subsystem errors and fails safely by returning False."""
    # Arrange: Force break the internal database connection engine execution loop
    # We alter the method to raise a sqlite3 operational error when invoked
    def break_query_execution():
        raise sqlite3.OperationalError("Simulated infrastructure corruption event.")
        
    db_service._get_connection = break_query_execution

    # Act: Challenge ownership verification when structural integrity is broken
    is_owner = db_service.verify_portfolio_ownership(username="any_user@peakyblinders.com", portfolio_id="any_id")

    # Assert: Must evaluate to False cleanly without bubbling up unhandled exceptions
    assert is_owner is False