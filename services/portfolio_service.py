import datetime
import logging
import yfinance as yf
from fastapi import HTTPException, status
from exceptions import StockNotFoundException, StockInfoNotFoundException, PortfolioException
from schemas import StockResponse, StocksResponse
from services.database_service import DatabaseService
from services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger("portfolio_app")

class PortfolioService:
    def __init__(self, database_service: DatabaseService):
        self.database_service = database_service
        self.exchange_rate_service = ExchangeRateService()
        logger.info("Initialized the Portfolio Service")

    def get_latest_price(self, ticker_symbol: str, portfolio_id: str) -> StockResponse:
        """Fetches live stock values and normalizes metrics into portfolio currency."""
        symbol_clean = ticker_symbol.upper().strip()
        
        # 1. Fetch metadata configuration from internal DB first
        info = self.database_service.get_stock(symbol_clean, portfolio_id)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset metadata {symbol_clean} not configured for user {portfolio_id}."
            )

        company = info.get("company", "Unknown Company")
        exchange = info.get("exchange", "Unknown Exchange")
        currency = info.get("currency", "USD").upper().strip()
        owned = info.get("owned", 0)
        cost = info.get("cost", 0.0)

        # 2. Resiliently fetch market data via yfinance
        try:
            ticker = yf.Ticker(symbol_clean)
            data = ticker.history(period="1d")
        except Exception as e:
            logger.error(f"Network / API failure fetching ticker {symbol_clean}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Market data provider unavailable for symbol {symbol_clean}."
            )

        # Protect against empty frames or missing rows before index parsing
        if data.empty or len(data) == 0:
            logger.warning(f"Ticker symbol {symbol_clean} returned no historic dataframe records.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pricing information returned for asset symbol {symbol_clean}."
            )

        try:
            open_price = float(data["Open"].iloc[-1])
            close_price = float(data["Close"].iloc[-1])
        except (IndexError, KeyError, ValueError) as e:
            logger.error(f"Malformed market structure matrix for {symbol_clean}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unable to parse open/close prices for {symbol_clean}."
            )

        # 3. Calculate financial metrics safely
        open_value = open_price * owned
        close_value = close_price * owned
        daily_change = close_value - open_value

        # Normalise evaluation currencies to standard structural metrics
        # LSE market assets are traded in GBp / GBX (Pence) requiring adjustment 
        if currency in ["GBP", "GBX", "GBPENCE"]:
            open_value /= 100
            close_value /= 100
            daily_change /= 100
            overall_change = close_value - cost
        else:
            try:
                exchange_rate = self.exchange_rate_service.get_exchange_rate(currency)
                if not exchange_rate or exchange_rate <= 0:
                    raise ValueError(f"Invalid rate scale: {exchange_rate}")
            except Exception as e:
                logger.error(f"Exchange rate failure for currency context {currency}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Currency exchange rate cross-matrix matching failed for {currency}."
                )
            
            close_value = close_value * exchange_rate
            daily_change = daily_change * exchange_rate
            overall_change = close_value - cost

        stock_date = datetime.datetime.now(datetime.timezone.utc).strftime("%d-%m-%Y %H:%M")

        return StockResponse(
            portfolio_id=portfolio_id,
            symbol=symbol_clean,
            company=company,
            exchange=exchange,
            owned=owned,
            cost=cost,
            currency=currency,
            date=stock_date,
            open_price=round(open_price, 4),
            close_price=round(close_price, 4),
            close_value=round(close_value, 2),
            daily_change=round(daily_change, 2),
            overall_change=round(overall_change, 2),
        )

    def get_portfolio_valuation(self, portfolio_id: str) -> StocksResponse | None:
        """Aggregates performance cross-checks across all active positions."""
        stocks = self.database_service.get_stocks(portfolio_id)

        if not stocks:
            return None
       
        compiled_data = []
        portfolio_position = 0.00
        portfolio_daily_position = 0.00

        for item in stocks:
            symbol = item.get("symbol")
            if not symbol:
                continue
                
            try:

                # Loop fault containment: Let individual asset lookup crashes stay localized
                stock_res = self.get_latest_price(symbol, portfolio_id)
    
                portfolio_position += stock_res.overall_change
                portfolio_daily_position += stock_res.daily_change
                compiled_data.append(stock_res)
            except HTTPException as http_ex:
                logger.warning(
                    f"Skipping valuation item for symbol {symbol} due to API/Data limitations: {http_ex.detail}"
                )
            except Exception as e:
                logger.error(
                    f"Unhandled fatal calculation bypass for ticker symbol {symbol}: {str(e)}"
                )

        return StocksResponse(
            portfolio_daily_position=round(portfolio_daily_position, 2),
            portfolio_position=round(portfolio_position, 2),
            stocks=compiled_data,
        )