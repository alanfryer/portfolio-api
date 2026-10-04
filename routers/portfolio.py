from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from schemas import StockInput, StockUpdateInput, StockResponse, StocksResponse
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
@router.get("/valuation", response_model=StocksResponse)
def get_live_portfolio_valuation(
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    """Calculates active daily valuation for the Stocks in the Portfolio."""

    return portfolio.get_portfolio_valuation(current_user["username"])


@router.get("/valuation/{symbol}", response_model=StockResponse)
def get_live_stock_valuation(
    symbol: str,
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    """Fetches real-time price changes for a single Stock in the Portfolio."""

    username = current_user["username"]

    return portfolio.get_latest_price(symbol, username)


# --- ASSET CONFIGURATION (CRUD) ROUTES ---
@router.get("/", response_model=list[StockInput])
def get_portfolio_stocks(
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Fetches all the Stocks in the Portfolio."""
    
    username = current_user["username"]
    stocks = db.get_portfolio(username)
    
    # --- EMPTY PORTFOLIO EXCEPTION CHECK ---
    if not stocks:
        raise PortfolioException(status=404, message= f"No Stocks found in the Portfolio for '{username}'.")
    
    return stocks


@router.get("/{symbol}", response_model=StockInput)
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
    stock: StockInput,
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

    return db.update_stock(symbol, update_data)


@router.delete("/{symbol}")
def delete_portfolio_stock(
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    """Delete a Stock from the Portfolio."""

    username = current_user["username"]

    return db.delete_stock(symbol)
