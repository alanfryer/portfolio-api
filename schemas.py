from pydantic import BaseModel, Field, SecretStr


class StockResponse(BaseModel):
    company: str
    exchange: str
    currency: str
    owned: int
    cost: float | None = 0.00
    date: str
    open_price: float | None = 0.00
    close_price: float | None = 0.00
    close_value: float | None = 0.00
    daily_change: float | None = 0.00
    overall_change: float | None = 0.00


class StocksResponse(BaseModel):
    portfolio_daily_position: float
    portfolio_position: float
    stocks: list[StockResponse]


class StockInput(BaseModel):
    symbol: str = Field(
        ..., example="AAPL", description="The stock ticker symbol (Primary Key)"
    )
    company: str = Field(..., example="Apple Inc.")
    exchange: str = Field(..., example="NASDAQ")
    currency: str = Field(..., example="USD")
    owned: float = Field(..., gt=0, example=10.5, description="Number of shares owned")
    cost: float = Field(
        ...,
        ge=0,
        example=1200.50,
        description="Total cost basis in base currency (GBP)",
    )


class StockUpdateInput(BaseModel):
    company: str | None = None
    exchange: str | None = None
    currency: str | None = None
    owned: float | None = Field(None, gt=0)
    cost: float | None = Field(None, ge=0)


class UserUpdateInput(BaseModel):
    password: str = Field(..., min_length=6)
