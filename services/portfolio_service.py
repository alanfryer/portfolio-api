import datetime
import logging
import requests
import yfinance as yf
from exceptions import StockNotFoundException, StockInfoNotFoundException
from schemas import StockResponse, StocksResponse
from services.database_service import DatabaseService
from services.exchange_rate_service import ExchangeRateService

# Setup standard structured logging instead of using print()
logger = logging.getLogger("portfolio_app")


class PortfolioService:
    def __init__(self, database_service: DatabaseService):
        self.database_service = database_service
        self.exchange_rate_service = ExchangeRateService()

        logger.info("Initialised the Market Service")

    def get_latest_price(self, ticker_symbol: str) -> StockResponse:
        """Fetches live stock values and normalizes metrics into portfolio currency."""
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period="1d")

        if data.empty:
            raise StockNotFoundException(symbol=ticker_symbol)

        info = self.database_service.get_portfolio_stock(ticker_symbol)
        if not info:
            raise StockInfoNotFoundException(symbol=ticker_symbol)

        # Destructure database row metrics
        company, exchange, currency = (
            info["company"],
            info["exchange"],
            info["currency"],
        )
        owned, cost = info["owned"], info["cost"]

        # Standardise date stamps on calculations to track timeline variations
        stock_date = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%d-%m-%Y %H:%M"
        )
        open_price = data["Open"].iloc[-1]
        close_price = data["Close"].iloc[-1]

        # Native currency calculations
        open_value = open_price * owned
        close_value = close_price * owned
        daily_change = close_value - open_value

        # Convert evaluation states to Base Currency Group (GBP)
        # Note: LSE market indicators are quoted in GBP (pence), requiring a division step
        if currency == "GBP":
            open_value /= 100
            close_value /= 100
            daily_change /= 100
            overall_change = close_value - cost
        else:
            # Query standard cross-rate matrices for non-local denominations
            exchange_rate = self.exchange_rate_service.get_exchange_rate(currency)
            close_value = close_value * exchange_rate
            daily_change = daily_change * exchange_rate
            overall_change = close_value - cost

        return StockResponse(
            company=company,
            exchange=exchange,
            owned=owned,
            cost=cost,
            currency=currency,
            date=stock_date,
            open_price=round(open_price, 2),
            close_price=round(close_price, 2),
            close_value=round(close_value, 2),
            daily_change=round(daily_change, 2),
            overall_change=round(overall_change, 2),
        )

    def get_portfolio_valuation(self) -> StocksResponse:
        """Aggregates performance cross-checks across all active positions."""
        stocks = self.database_service.get_portfolio()
        compiled_data = []
        portfolio_position = 0.00
        portfolio_daily_position = 0.00

        for item in stocks:
            try:
                stock_res = self.get_latest_price(item["symbol"])
                portfolio_position += stock_res.overall_change
                portfolio_daily_position += stock_res.daily_change
                compiled_data.append(stock_res)
            except Exception as e:
                # Prevent one failed API connection from crashing the entire calculation pipeline
                logger.error(
                    f"Skipping aggregation calculation for ticker {item.get('symbol')}: {e}"
                )

        return StocksResponse(
            portfolio_daily_position=round(portfolio_daily_position, 2),
            portfolio_position=round(portfolio_position, 2),
            stocks=compiled_data,
        )