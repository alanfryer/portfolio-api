import logging
from fastapi import APIRouter, status, Depends, Response, HTTPException
from schemas import Stock, StockBase, StockUpdateInput, StockResponse, StocksResponse

from services.authorization_service import authenticate
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

async def authorize(
    portfolio_id: str,
    db: DatabaseService = Depends(get_db_service),
    authenticated_user: dict = Depends(authenticate)
) -> dict:
    """
    Verifies that the authenticated user owns the specified portfolio.
    """
    user = authenticated_user["username"]
    if not db.verify_portfolio_ownership(authenticated_user["username"], portfolio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to the Portfolio '{portfolio_id}' is not allowed by the user '{user}."
        )
        
    logger.info(f"Successfully authenticated: {authenticated_user}")
    return authenticated_user

# --- LIVE PERFORMANCE ROUTES ---
@router.get("/{portfolio_id}", response_model=StocksResponse | list[Stock])
def get_live_portfolio_valuation(
    portfolio_id: str,
    view: str | None = None,
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    authenticated: dict = Depends(authorize),
):
        
    if view == "valuation":
        try:
            valuation_data = portfolio.get_portfolio_valuation(portfolio_id)
        except Exception as e:
            logger.error(f"Valuation service failed for user {portfolio_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail="Failed to retrieve real-time external valuation metrics."
            )
        
        if not valuation_data:
            # Fixed Status Code: Use 404 instead of 200 for missing target resources
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"No Stocks found in the Portfolio for user '{portfolio_id}'."
            )
        return valuation_data
    
    return db.get_portfolio(portfolio_id)
    
@router.get("/{portfolio_id}/{symbol}", response_model=StockResponse | StockBase)
def get_stock(
    portfolio_id: str,
    symbol: str,
    view: str | None = None,
    db: DatabaseService = Depends(get_db_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    authenticated: dict = Depends(authorize),
):

    symbol_upper = symbol.upper().strip()
    suffix_msg = f"the Stock '{symbol_upper}' in the Portfolio owned by {portfolio_id}"

    if view == "valuation":
        try:
            live_price = portfolio.get_latest_price(symbol_upper, portfolio_id)
        except HTTPException as e:
            error_msg = f"Live price lookup failed for {suffix_msg}."
            logger.error(error_msg)
            raise HTTPException(
                status_code=e.status_code, 
                detail=error_msg
            )

        if not live_price:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Real-time pricing unavailable for {suffix_msg}."
            )
        return live_price
    
    stock = db.get_stock(symbol_upper, portfolio_id)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{suffix_msg} not found."
        )

    return stock


@router.post("/{portfolio_id}", status_code=status.HTTP_201_CREATED)
def add_stock_to_portfolio(
    stock: Stock,
    portfolio_id: str,    
    db: DatabaseService = Depends(get_db_service),
    authenticated: dict = Depends(authorize),
   
):

    stock.symbol = stock.symbol.upper().strip()

    existing_stock = db.get_stock(stock.symbol, portfolio_id)

    if existing_stock:
        # Fixed Status Code: 409 Conflict accurately represents resource duplication collisions
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stock {stock.symbol} already exists in the Portfolio for '{portfolio_id}'. Use PUT to modify it."
        )

    db.add_stock(stock, portfolio_id)
    return {"message": f"Stock {stock.symbol} successfully added.", "symbol": stock.symbol}


@router.put("/{portfolio_id}/{symbol}", status_code=status.HTTP_200_OK)
def update_portfolio_stock(
    portfolio_id: str,
    symbol: str,
    update_data: StockUpdateInput,
    db: DatabaseService = Depends(get_db_service),
    authenticated: dict = Depends(authorize),    
):

    symbol_upper = symbol.upper().strip()

    stock = db.get_stock(symbol_upper, portfolio_id)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The Stock '{symbol_upper}' does not exist in the Portfolio for {portfolio_id}."
        )

    db.update_stock(symbol_upper, portfolio_id, update_data)
    return {"message": f"Stock {symbol_upper} updated successfully."}


@router.delete("/{portfolio_id}/{symbol}")
def delete_portfolio_stock(
    portfolio_id: str,
    symbol: str,
    db: DatabaseService = Depends(get_db_service),
    authenticated: dict = Depends(authorize),  
):
        
    symbol_upper = symbol.upper().strip()

    stock = db.get_stock(symbol_upper, portfolio_id)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The Stock '{symbol_upper}' does not exist in the Portfolio for {portfolio_id}."
        )

    db.delete_stock(symbol_upper, portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)