import sqlite3
import logging
import bcrypt
from fastapi import HTTPException, status
from pydantic import SecretStr 
from schemas import Portfolio, Stock, User, StockBase, StockUpdateInput, UserUpdateInput

logger = logging.getLogger("portfolio_app")

class DatabaseService:
    def __init__(self):
        self.db_path = "/home/alanfryer/sqlite/portfolio.db"
        logger.info("Initialized the Database Service")

    def _get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as e:
            logger.critical(f"Database connection engine failed at target path: {self.db_path}. Error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database subsystem connection failure."
            )

    def _handle_db_error(self, contextual_msg: str, exception: Exception):
        """Centralized logging helper to abstract relational errors away from client payloads."""
        error_msg =f"{contextual_msg} | SQL Trace: {str(exception)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_msg
        )

    def _get_password_hash(self, password: SecretStr) -> str:
        """Extracts the raw password from SecretStr and hashes it securely."""
        try:
            # Safely extract the secret string value before encoding
            raw_password = password.get_secret_value()
            password_bytes = raw_password.encode("utf-8")
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password_bytes, salt).decode("utf-8")
        except Exception as e:
            logger.error(f"Crypto failure during string processing: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security framework processing failure."
            )
    
    # --- PORTFOLIO OPERATIONS ---
    def get_portfolios(self) -> list[Portfolio]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, username, created_at FROM portfolios;",
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching the Portfolios.", e)

    def get_portfolio(self, portfolio_id: str) -> dict | None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, username, created_at FROM portfolios WHERE id = ?;",
                    (portfolio_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching the Portfolio information for '{portfolio_id}'.", e)
    
    def add_portfolio(self, portfolio: Portfolio) -> None:
        """Inserts Portfolio directly. Relies on higher-level verification for duplicates."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO portfolios (id, name, username)
                    VALUES (?, ?, ?);
                    """,
                    (
                        portfolio.id,
                        portfolio.name,
                        portfolio.username
                    ),
                )
                conn.commit()
 
        except sqlite3.Error as e:
            self._handle_db_error(f"Database insertion problem for the Portfolio '{portfolio.id}'.", e)

    def delete_portfolio(self, portfolio_id: str) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM portfolios WHERE id = ?;", (portfolio_id,))

                conn.commit()
        except sqlite3.Error as e:
            raise self._handle_db_error(f"Database deletion problem for the Portfolio '{portfolio_id}'.", e)
    
    def get_stocks(self, portfolio_id: str) -> list[StockBase]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, company, exchange, currency, owned, cost, portfolio_id FROM stocks WHERE portfolio_id = ?;",
                    (portfolio_id,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching the Stocks for Portfolio '{portfolio_id}'", e)

    def get_stock(self, symbol: str, portfolio_id: str) -> dict | None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, company, exchange, currency, owned, cost FROM stocks WHERE symbol = ? AND portfolio_id = ?;",
                    (symbol.upper().strip(), portfolio_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching the Stock information for '{symbol}' in the Portfolio '{portfolio_id}'", e)

    def add_stock(self, stock: Stock, portfolio_id: str) -> None:
        """Inserts stock configurations directly. Relies on higher-level verification for duplicates."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO stocks (symbol, portfolio_id, company, exchange, currency, owned, cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        stock.symbol.upper().strip(),
                        portfolio_id,
                        stock.company,
                        stock.exchange,
                        stock.currency.upper().strip(),
                        stock.owned,
                        stock.cost
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            self._handle_db_error(f"Database insertion problem for the stock {stock.symbol}, in the Portfolio for {portfolio_id}", e)

    def update_stock(self, symbol: str, portfolio_id: str, update_data: StockUpdateInput) -> None:
        fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
        
        if not fields:
            raise self._handle_db_error("No fields provided for update", e)

        if "currency" in fields:
            fields["currency"] = fields["currency"].upper()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clause = ", ".join([f"{key} = ?" for key in fields.keys()])
                values = list(fields.values()) + [symbol.upper()] + [portfolio_id]
                cursor.execute(
                    f"UPDATE stocks SET {set_clause} WHERE symbol = ? AND portfolio_id = ?;", values,
                )

                conn.commit()

        except sqlite3.Error as e:
            self._handle_db_error(f"Database update problem for stock={symbol}, portfolio={portfolio_id}", e)


    def delete_stock(self, symbol: str, portfolio_id: str) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM stocks WHERE symbol = ? and portfolio_id = ?;", (symbol.upper(), portfolio_id,))

                conn.commit()
        except sqlite3.Error as e:
            raise self._handle_db_error(f"Database removal task failed for stock={symbol}, portfolio={portfolio_id}", e)


    # --- USER OPERATIONS ---
    def register_user(self, username: str, password: SecretStr, scopes: list[str]) -> User:
        """Validates availability and registers a new user securely into SQLite."""
        hashed_password = self._get_password_hash(password)
        # Store scopes as a simple comma-separated string for SQLite simplicity
        scopes_str = ",".join(scopes)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, hashed_password, scopes) VALUES (?, ?, ?)",
                    (username, hashed_password, scopes_str),
                )
                conn.commit()
                return User(username=username, password=password, scopes=scopes)
        except sqlite3.IntegrityError as e:
            raise self._handle_db_error(f"The User '{username}' is already registered.", e)

    def delete_user(self, username: str) -> None:
        """Deletes a user from SQLite."""

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
                conn.commit()
                
        except sqlite3.Error as e:
            raise self._handle_db_error(f"Failed to delete the User '{username}'.", e)


    def get_user(self, username: str) -> dict | bool:
        """Validates credentials against stored SQLite records."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row  # Returns results as dictionary-like objects
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()

        if not user:
            return False

        return {
            "username": user["username"],
            "hashed_password": user["hashed_password"],
            "scopes": user["scopes"].split(","),  # Convert back to list format
        }



    def update_user_password(self, username: str, update_data: UserUpdateInput) -> dict:
        """Hashes and updates a user's password securely in SQLite."""
        # Ensure password is provided in the update payload
        if not update_data.password:
            raise self._handle_db_error(f"Password field is required for update. the User '{username}'.", e)

        hashed_password = self._get_password_hash(update_data.password)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET hashed_password = ? WHERE username = ?;",
                    (hashed_password, username),
                )

                conn.commit()

        except sqlite3.Error as e:
            raise self._handle_db_error(f"Failed to update password for the User '{username}'.", e)
        
    def verify_portfolio_ownership(self, username: str, portfolio_id: str) -> bool:
        """Security guard checking if the token user owns the portfolio resource."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM portfolios WHERE id = ? AND username = ?", 
                    (portfolio_id, username)
                )
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

