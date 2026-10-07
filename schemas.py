from pydantic import BaseModel, Field, SecretStr
from typing import List, Optional

class StockBase(BaseModel):
    symbol: str 
    company: str
    exchange: str
    currency: str
    owned: float
    cost: float

class Stock(StockBase):
    #id: Optional[int] = None
    portfolio_id: str = Field(..., description="The parent portfolio identifier this asset belongs to")

    class Config:
        from_attributes = True  # Allows parsing SQLite Row objects directly

class StockResponse(Stock):
    date: str
    open_price: float
    close_price: float
    close_value: float
    daily_change: float
    overall_change: float        

class StocksResponse(BaseModel):
    portfolio_daily_position: float
    portfolio_position: float
    stocks: list[StockResponse]

class StockUpdateInput(BaseModel):
    company: str | None = None
    exchange: str | None = None
    currency: str | None = None
    owned: float | None = Field(None, gt=0)
    cost: float | None = Field(None, ge=0)


class UserUpdateInput(BaseModel):
    password: str = Field(..., min_length=6)
