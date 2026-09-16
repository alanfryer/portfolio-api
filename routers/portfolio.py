from fastapi import APIRouter, HTTPException, status, Depends
from schemas import StockInput, StockUpdateInput, StockResponse, StocksResponse
from services.db_service import DatabaseService
from services.market_service import MarketService

router = APIRouter(prefix="/v1/portfolio", tags=["Portfolio Management"])


# 1. Dependency to yield or get your Database Instance
def get_db_service() -> DatabaseService:
    return DatabaseService()


def get_market_service(
    db_service: DatabaseService = Depends(get_db_service),
) -> MarketService:
    return MarketService(db_service)


# --- LIVE PERFORMANCE ROUTES ---
@router.get("/valuation", response_model=StocksResponse)
def get_live_portfolio_valuation(market: MarketService = Depends(get_market_service)):
    """Calculates active daily valuation for the Stocks in the Portfolio."""
    return market.get_portfolio_valuation()


@router.get("/valuation/{symbol}", response_model=StockResponse)
def get_live_stock_valuation(
    symbol: str, market: MarketService = Depends(get_market_service)
):
    """Fetches real-time price changes for a single Stock in the Portfolio."""
    return market.get_latest_price(symbol)


# --- ASSET CONFIGURATION (CRUD) ROUTES ---
@router.get("/", response_model=list[StockInput])
def get_portfolio_stocks(db: DatabaseService = Depends(get_db_service)):
    """Fetches all the Stocks in the Portfolio."""
    return db.get_all_stocks()


@router.get("/{symbol}", response_model=StockInput)
def get_portfolio_stock(symbol: str, db: DatabaseService = Depends(get_db_service)):
    """Fetches a Stock from the Portfolio."""
    stock = db.get_stock_by_symbol(symbol)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock configuration for '{symbol}' not found.",
        )
    return stock


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_stock_to_portfolio(
    stock: StockInput, db: DatabaseService = Depends(get_db_service)
):
    """Add a Stock to the Portfolio."""
    return db.add_stock(stock)


@router.put("/{symbol}")
def update_portfolio_stock(
    symbol: str,
    update_data: StockUpdateInput,
    db: DatabaseService = Depends(get_db_service),
):
    """Update a Stock in the Portfolio."""
    return db.update_stock(symbol, update_data)


@router.delete("/{symbol}")
def delete_portfolio_stock(symbol: str, db: DatabaseService = Depends(get_db_service)):
    """Delete a Stock from the Portfolio."""
    return db.delete_stock(symbol)
