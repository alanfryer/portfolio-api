from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from services.auth_service import AuthService, ACCESS_TOKEN_EXPIRE_MINUTES
from services.db_service import DatabaseService
from schemas import UserUpdateInput
import datetime

router = APIRouter(prefix="/v1/users", tags=["Authentication"])


# --- DEPENDENCY INJECTORS ---
def get_db_service() -> DatabaseService:
    return DatabaseService()


def get_auth_service() -> AuthService:
    return AuthService()


class UserRegisterSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_portfolio_user(
    user_data: UserRegisterSchema, db: DatabaseService = Depends(get_db_service)
):
    """Register a new User for accessing the Portfolio."""
    return db.register_user(user_data.username, user_data.password)


@router.delete("/{username}")
def delete_portfolio_user(username: str, db: DatabaseService = Depends(get_db_service)):
    """Delete a User from the Portfolio."""
    return db.delete_user(username)


@router.put("/{username}")
def update_portfolio_user_password(
    username: str,
    update_data: UserUpdateInput,
    db: DatabaseService = Depends(get_db_service),
):
    """Update the Password for the Portfolio User."""
    return db.update_user_password(username, update_data)


@router.post("/token")
async def get_jwt_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Validates the User credentials and returns a JWT Token valid for 30 minutes.
    Accepts application/x-www-form-urlencoded inputs (username & password).
    """
    return auth.create_access_token(form_data.username, form_data.password)
