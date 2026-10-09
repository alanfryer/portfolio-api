import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import SecretStr
from services.authorization_service import authorize
from services.authorization_service import authenticate
from services.authorization_service import AuthorizationService, ACCESS_TOKEN_EXPIRE_MINUTES
from services.database_service import DatabaseService
from schemas import UserUpdateInput, User

logger = logging.getLogger("portfolio_app")
router = APIRouter(prefix="/v1/users", tags=["Authentication"])

# --- DEPENDENCY INJECTORS ---
def get_db_service() -> DatabaseService:
    return DatabaseService()

def get_auth_service() -> AuthorizationService:
    return AuthorizationService()

@router.post("/", status_code=status.HTTP_201_CREATED)
def add_user(
    user_data: User, 
    db: DatabaseService = Depends(get_db_service)
):
    """Register a new User for accessing the Portfolio."""

    return db.register_user(user_data.username, user_data.password, user_data.scopes)

@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(username: str, 
                db: DatabaseService = Depends(get_db_service),
                authenticated: dict = Depends(authorize)):
    """Delete a User from the Portfolio."""
    
    user = db.get_user(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The user '{username}' does not exist."
        )

    db.delete_user(username)
    logger.info(f"Deleted User '{username}'.")
    

@router.put("/{username}")
def update_user_password(
    username: str,
    update_data: UserUpdateInput,
    db: DatabaseService = Depends(get_db_service),
    authenticated: dict = Depends(authorize)
):
    """Update the Password for the Portfolio User."""

    user = db.get_user(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The user '{username}' does not exist."
        )
    
    db.update_user_password(username, update_data)
    logger.info(f"Password for User '{username}' updated.")


@router.post("/token")
async def get_jwt_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth: AuthorizationService = Depends(get_auth_service),
    authenticated: dict = Depends(authenticate)
):
    """
    Validates the User credentials and returns a JWT Token valid for 30 minutes.
    Accepts application/x-www-form-urlencoded inputs (username & password).
    """
    password = SecretStr(form_data.password)
    return auth.create_access_token(form_data.username, password)
