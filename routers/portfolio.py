from fastapi import APIRouter, status, Depends, Response
from schemas import Stock, StockUpdateInput, StockResponse, StocksResponse
from exceptions import StockNotFoundException, StockInfoNotFoundException, PortfolioException
from services.authorization_service import get_current_user
from services.database_service import DatabaseService
from services.portfolio_service import PortfolioService

router = APIRouter(prefix="/v1/portfolio", tags=["Portfolio Management"])

# 1. Dependency to yield or get your Database Instance
def get_db_service() -> DatabaseService:
    return DatabaseService()


def get_portfolio_service(
    db_service: DatabaseService = Depends(get_db_service),
) -> PortfolioService:
    return PortfolioService(db_service)


# --- LIVE PERFORMANCE ROUTES ---
@router.get("/", response_model=StocksResponse |list[Stock])
def get_live_portfolio_valuation(
    view: str | None = None,  # Optional query param to handle valuations dynamically
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):

    username = current_user["username"]    

    if view == "valuation":
        valuation_data = portfolio.get_portfolio_valuation(username)
        
        if not valuation_data:
            raise PortfolioException(status=200, message= f"No Stocks found in the Portfolio for '{username}'.")
        return valuation_data
    
    stocks = db.get_portfolio(username)
    
    # Standard REST Practice: Return empty list [] if user owns no stock instead of raising an error
    return stocks if stocks is not None else []

@router.get("/{symbol}", response_model=StockResponse | Stock)
def get_portfolio_stock(
    symbol: str,
    view: str | None = None,
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Unified Single Stock Fetcher (Fixed Path Collision).
    - Default view: Fetches a specific configuration Stock from the database.
    - ?view=valuation: Fetches real-time price updates and changes for the specific asset.
    """
    username = current_user["username"]
    symbol_upper = symbol.upper()

    # 1. Handle live valuation request
    if view == "valuation":
        live_price = portfolio.get_latest_price(symbol_upper, username)

        if not live_price:
            raise StockInfoNotFoundException(message=f"Real-time pricing unavailable for asset {symbol_upper}.")
        return live_price
    

    # 2. Handle standard database asset request
    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise StockInfoNotFoundException(symbol=symbol_upper, username=username)

    return stock

@router.post("/", status_code=status.HTTP_201_CREATED)
def add_stock_to_portfolio(
    stock: Stock,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Adds a new Stock asset configuration to the user's Portfolio."""
    # Ensure consistency by locking down ownership parameters manually 
    username = current_user["username"]
    
    # Check if stock already exists to prevent duplicate items
    existing_stock = db.get_portfolio_stock(stock.symbol.upper(), username)
    if existing_stock:
        raise PortfolioException(status=200, message= f"Stock {stock.symbol.upper()} already exists in the Portfolio for '{username}'. Use PUT to modify it.")

    return db.add_stock(stock)


@router.put("/{symbol}", status_code=200)
def update_portfolio_stock(
    symbol: str,
    update_data: StockUpdateInput,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Updates configuration details of a specific Stock in the user's Portfolio."""
    username = current_user["username"]
    symbol_upper = symbol.upper()

    # Check existence before executing an atomic write/update operation
    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise StockInfoNotFoundException(symbol=symbol_upper, username=username)


    return db.update_stock(symbol_upper, username, update_data)

@router.delete("/{symbol}")
def delete_portfolio_stock(
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Delete a Stock from the Portfolio."""

    username = current_user["username"]
    symbol_upper = symbol.upper()

    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise StockInfoNotFoundException(symbol=symbol_upper, username=username)

    db.delete_stock(symbol_upper, username)
    
    # REST best practice for deletions: Return 204 No Content with a completely blank HTTP body
    return Response(status_code=status.HTTP_204_NO_CONTENT)