import datetime
import base64
import bcrypt  # Use native bcrypt directly
import jwt
import logging
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from jwt.exceptions import ExpiredSignatureError
from services.database_service import DatabaseService

# Configuration (Keep environment variables in production)
SECRET_KEY = "your-super-secret-and-random-signing-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Setup standard structured logging instead of using print()
logger = logging.getLogger("portfolio_app")


class AuthService:
    def __init__(self):
        self.database_service = DatabaseService()
        logger.info("Initialised the Market Service")

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hashes a plain text password safely using native bcrypt."""
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed_bytes = bcrypt.hashpw(password_bytes, salt)
        return hashed_bytes.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies a plain text password against a stored bcrypt hash string."""
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except Exception as e:
            return False

    def create_access_token(self, username: str, password: str) -> str:
        """Generates a secure JSON Web Token."""

        user = self.authenticate_user(username, password)

        if not user:
            raise self.create_auth_exception(
                detail="Failed to create JWT Token, incorrect username or password entered.",
                scheme="Bearer",
            )

        # Set token expiration time
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode = {"sub": user["username"], "scopes": user["scopes"], "exp": expire}
        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        return {"access_token": token, "token_type": "bearer"}

    async def get_current_user(self, request: Request) -> dict:
        """
        FastAPI Dependency that dynamically checks the Authorization header.
        Automatically fixes and handles dynamic Base64 padding structures safely.
        """
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            raise Exception("No Authorization Header")

        scheme, param = get_authorization_scheme_param(auth_header)

        # ==========================================
        # CASE A: BASIC AUTHENTICATION (Base64)
        # ==========================================
        if scheme.lower() == "basic":
            try:
                missing_padding = len(param) % 4
                if missing_padding:
                    param += "=" * (4 - missing_padding)

                decoded_bytes = base64.b64decode(param)
                decoded_str = decoded_bytes.decode("utf-8")

                if ":" not in decoded_str:
                    raise self.create_auth_exception(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Missing delimiter from Base64 encoded credentials",
                        scheme="Basic",
                    )

                username, password = decoded_str.split(":", 1)

            except Exception as e:
                raise self.create_auth_exception(
                    detail=f"Invalid Base64 encoding structure {e}", scheme="Basic"
                )

            user = self.authenticate_user(username, password)

            if user is None:
                raise self.create_auth_exception(
                    detail="Failed authentication.", scheme="Basic"
                )

            return {
                "username": user["username"],
                "scopes": user["scopes"],
                "auth_method": "basic",
            }

        # ==========================================
        # CASE B: BEARER TOKEN (JWT)
        # ==========================================
        elif scheme.lower() == "bearer":
            try:
                payload = jwt.decode(param, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")

                if username is None:
                    raise self.create_auth_exception(
                        detail="Could not get the username from the JWT Token.",
                        scheme="Bearer",
                    )

                return {
                    "username": username,
                    "scopes": payload.get("scopes", []),
                    "auth_method": "bearer",
                }

            except ExpiredSignatureError as exp:
                raise self.create_auth_exception(
                    detail=f"JWT Token Error: {exp}", scheme="Bearer"
                )
            except jwt.PyJWTError as exp:
                raise self.create_auth_exception(
                    detail=f"Error parsing the JWT Token: {exp}", scheme="Bearer"
                )


    def authenticate_user(self, username, password):
        user = self.database_service.get_user(username)

        if not user:
            raise self.create_auth_exception(
                detail=f"The User '{username}' has not been registered", scheme="Bearer"
            )

        if not self.verify_password(password, user["hashed_password"]):
            self.create_auth_exception(
                detail=f"Password verification failed for the User '{user["username"]}'",
                scheme="Bearer",
            )

        return user

    def create_auth_exception(
        self, detail: str, scheme: str, status_code: int = status.HTTP_401_UNAUTHORIZED
    ):
        logger.error(detail)

        raise HTTPException(
            status_code=status_code,
            detail=detail,
            headers={"WWW-Authenticate": scheme},
        )
