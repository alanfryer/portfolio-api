import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from services.auth_service import AuthService
from routers import exchange_rates, portfolio, auth
from exceptions import StockNotFoundException, StockInfoNotFoundException, PortfolioException
from services.db_service import DatabaseService

# Initialise FastAPI application with custom lifespan tracking
app = FastAPI(title="Portfolio Checker API")

# 1. Yield or get your Database Instance
def get_db_service() -> DatabaseService:
    return DatabaseService()

# 2. Yield or get your AuthService instance with the injected DB
def get_auth_service(db_service: DatabaseService = Depends(get_db_service)) -> AuthService:
    return AuthService()

# 3. Wrapper dependency that resolves the 'self' parameter for your class method
async def auth_dependency(request: Request, auth_service: AuthService = Depends(get_auth_service)) -> dict:
    """
    Acts as the entry gate for router global protection.
    Resolves request and auth_service dynamically to execute the method cleanly.
    """
    return await auth_service.get_current_user(request)

# ==========================================
# CENTRALIZED LOGGING STRUCTURE
# ==========================================
# Configure standard formatting for application logs
log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Stream handler to output logs cleanly to the console standard output
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# Create a master root tracker for your portfolio app module
logger = logging.getLogger("portfolio_app")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Prevent log messages from bubbling up and duplicating in the Uvicorn defaults
logger.propagate = False

# ==========================================
# EXCEPTION HANDLERS
# ==========================================

@app.exception_handler(StockNotFoundException)
async def stock_not_found_exception_handler(request: Request, exc: StockNotFoundException):
    """Fired when yfinance returns empty data for an invalid or unlisted ticker symbol."""

    error_msg = f"The Stock prices for the symbol: {exc.symbol} could not be found."
    logger.error(error_msg)

    return JSONResponse(
        status_code=404,
        content={"message": error_msg},
    )

@app.exception_handler(StockInfoNotFoundException)
async def stock_info_not_found_exception_handler(request: Request, exc: StockInfoNotFoundException):
    """Fired when a valid ticker is requested but missing from the local configuration layout."""

    error_msg = f"The Stock Information for symbol: {exc.symbol} does not exist in the file 'portfolio.json'."
    logger.error(error_msg)


    return JSONResponse(
        status_code=404,
        content={"message": error_msg},
    )

@app.exception_handler(PortfolioException)
async def portfolio_exception_handler(request: Request, exc: PortfolioException):
    """Generic fallback handler for structural exceptions mapping across data mutations."""

    error_msg = f"{exc.message}."
    logger.error(error_msg)

    return JSONResponse(
        status_code=exc.status,
        content={"message": error_msg},
    )

# ==========================================
# ROUTER INCLUSIONS
# ==========================================

# 1. Include Auth Router (Kept completely PUBLIC so users can sign up and login)
app.include_router(auth.router)

# 2. Include Data Routers (Fully PROTECTED using our resolved authentication helper)
app.include_router(exchange_rates.router, dependencies=[Depends(auth_dependency)])
app.include_router(portfolio.router, dependencies=[Depends(auth_dependency)])

# ==========================================
# ROOT ENDPOINTS
# ==========================================

@app.get("/")
async def root():
    """Simple health-check baseline verification landing path."""
    return {"message": "API is running. Go to /docs for interactive documentation."}
