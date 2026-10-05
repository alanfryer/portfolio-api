import logging
from fastapi import APIRouter, status, Depends, Response, HTTPException
from schemas import Stock, StockUpdateInput, StockResponse, StocksResponse
from exceptions import StockNotFoundException, StockInfoNotFoundException, PortfolioException
from services.authorization_service import get_current_user
from services.database_service import DatabaseService
from services.portfolio_service import PortfolioService

logger = logging.getLogger("portfolio_app")
router = APIRouter(prefix="/v1/portfolio", tags=["Portfolio Management"])

def get_db_service() -> DatabaseService:
    return DatabaseService()

def get_portfolio_service(
    db_service: DatabaseService = Depends(get_db_service),
) -> PortfolioService:
    return PortfolioService(db_service)


# --- LIVE PERFORMANCE ROUTES ---
@router.get("/", response_model=StocksResponse | list[Stock])
def get_live_portfolio_valuation(
    view: str | None = None,
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]    

    if view == "valuation":
        try:
            valuation_data = portfolio.get_portfolio_valuation(username)
        except Exception as e:
            logger.error(f"Valuation service failed for user {username}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail="Failed to retrieve real-time external valuation metrics."
            )
        
        if not valuation_data:
            # Fixed Status Code: Use 404 instead of 200 for missing target resources
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"No Stocks found in the Portfolio valuation for user '{username}'."
            )
        return valuation_data
    
    stocks = db.get_portfolio(username)
    return stocks if stocks is not None else []


@router.get("/{symbol}", response_model=StockResponse | Stock)
def get_portfolio_stock(
    symbol: str,
    view: str | None = None,
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    symbol_upper = symbol.upper().strip()

    if view == "valuation":
        try:
            live_price = portfolio.get_latest_price(symbol_upper, username)
        except HTTPException as e:
            logger.error(f"Live price lookup failed for {symbol_upper} owned by {username}: {e.detail}")
            raise HTTPException(
                status_code=e.status_code, 
                detail= f"Live price lookup failed for {symbol_upper} owned by {username}: {e.detail}"
            )

        if not live_price:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Real-time pricing unavailable for asset {symbol_upper}."
            )
        return live_price
    
    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol_upper} not found in portfolio for user {username}."
        )

    return stock


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_stock_to_portfolio(
    stock: Stock,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    stock.symbol = stock.symbol.upper().strip()
    stock.username = username # Security Force: Overwrite payload variance to protect current user bounds
    
    existing_stock = db.get_portfolio_stock(stock.symbol, username)
    if existing_stock:
        # Fixed Status Code: 409 Conflict accurately represents resource duplication collisions
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stock {stock.symbol} already exists in the Portfolio for '{username}'. Use PUT to modify it."
        )

    db.add_stock(stock)
    return {"message": f"Stock {stock.symbol} successfully added.", "symbol": stock.symbol}


@router.put("/{symbol}", status_code=status.HTTP_200_OK)
def update_portfolio_stock(
    symbol: str,
    update_data: StockUpdateInput,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    symbol_upper = symbol.upper().strip()

    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol_upper} matching user context not found."
        )

    db.update_stock(symbol_upper, username, update_data)
    return {"message": f"Stock {symbol_upper} updated successfully."}


@router.delete("/{symbol}")
def delete_portfolio_stock(
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    symbol_upper = symbol.upper().strip()

    stock = db.get_portfolio_stock(symbol_upper, username)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol_upper} matching user context not found."
        )

    db.delete_stock(symbol_upper, username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)