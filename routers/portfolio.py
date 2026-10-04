from fastapi import APIRouter, status, Depends
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
    """Calculates active daily valuation for the Stocks in the Portfolio."""
    if view == "valuation":
        return portfolio.get_portfolio_valuation(current_user["username"])
    
    username = current_user["username"]
    stocks = db.get_portfolio(username)
    
    return stocks

@router.get("/{symbol}", response_model=StockResponse)
def get_live_stock_valuation(
    symbol: str,
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    """Fetches real-time price changes for a single Stock in the Portfolio."""

    username = current_user["username"]

    return portfolio.get_latest_price(symbol, username)


@router.get("/{symbol}", response_model=Stock)
def get_portfolio_stock(
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Fetches a Stock from the Portfolio."""

    username = current_user["username"]

    stock = db.get_portfolio_stock(symbol, username)
    
    if not stock:
        raise StockInfoNotFoundException(symbol=symbol, username=username)

    return stock


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_stock_to_portfolio(
    stock: Stock,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Add a Stock to the Portfolio."""

    username = current_user["username"]

    return db.add_stock(stock)

@router.put("/{symbol}")
def update_portfolio_stock(
    symbol: str,
    update_data: StockUpdateInput,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Update a Stock in the Portfolio."""

    username = current_user["username"]

    return db.update_stock(symbol, username, update_data)


@router.delete("/{symbol}")
def delete_portfolio_stock(
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Delete a Stock from the Portfolio."""

    username = current_user["username"]

    return db.delete_stock(symbol, username)
