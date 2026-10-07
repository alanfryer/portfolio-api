from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from services.authorization_service import AuthorizationService, ACCESS_TOKEN_EXPIRE_MINUTES
from services.database_service import DatabaseService
from schemas import UserUpdateInput, User
import datetime

router = APIRouter(prefix="/v1/users", tags=["Authentication"])


# --- DEPENDENCY INJECTORS ---
def get_db_service() -> DatabaseService:
    return DatabaseService()


def get_auth_service() -> AuthorizationService:
    return AuthorizationService()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_user(
    user_data: User, db: DatabaseService = Depends(get_db_service)
):
    """Register a new User for accessing the Portfolio."""
    print(user_data.scopes)
    db.register_user(user_data.username, user_data.password, user_data.scopes)
    return {"message": f"User {user_data.username} successfully added."}

@router.delete("/{username}")
def delete_user(username: str, db: DatabaseService = Depends(get_db_service)):
    """Delete a User from the Portfolio."""
    
    user = db.get_user(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The user '{username}' does not exist."
        )

    db.delete_user(username)
    return {"message": f"User {username} successfully deleted."}

@router.put("/{username}")
def update_user_password(
    username: str,
    update_data: UserUpdateInput,
    db: DatabaseService = Depends(get_db_service),
):
    """Update the Password for the Portfolio User."""

    user = db.get_user(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The user '{username}' does not exist."
        )
    
    db.update_user_password(username, update_data)
    return {"message": f"User {username} successfully updated."}


@router.post("/token")
async def get_jwt_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth: AuthorizationService = Depends(get_auth_service),
):
    """
    Validates the User credentials and returns a JWT Token valid for 30 minutes.
    Accepts application/x-www-form-urlencoded inputs (username & password).
    """
    return auth.create_access_token(form_data.username, form_data.password)
