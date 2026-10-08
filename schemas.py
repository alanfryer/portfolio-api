from typing import Annotated, List
from pydantic import BaseModel, BeforeValidator, Field, EmailStr, SecretStr
# 1. Define allowed scopes
ALLOWED_SCOPES = {"admin", "view", "add", "update", "delete"}

# 2. Validator function to check list items
def validate_list_scopes(v: any) -> List[str]:
    # Handle comma-delimited string input by converting it to a list first
    if isinstance(v, str):
        items = [s.strip() for s in v.split(",") if s.strip()]
    elif isinstance(v, list):
        items = [str(s).strip() for s in v]
    else:
        raise ValueError("Input must be a list or a comma-separated string")

    # Check each item against the allowed set
    invalid_items = [item for item in items if item not in ALLOWED_SCOPES]
    if invalid_items:
        raise ValueError(
            f"Invalid scope(s) found: {', '.join(invalid_items)}. "
            f"Allowed options are: {', '.join(ALLOWED_SCOPES)}"
        )
        
    return items

# 3. Create the type alias
AnyScopeList = Annotated[List[str], BeforeValidator(validate_list_scopes)]

# 4. Apply it to your schema
class User(BaseModel):
    username: EmailStr
    password: str = Field(..., min_length=6),
    scopes: AnyScopeList
       
class StockBase(BaseModel):
    symbol: str 
    company: str
    exchange: str
    currency: str
    owned: float
    cost: float

class Stock(StockBase):
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
