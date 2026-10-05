import sqlite3
import logging
import bcrypt
from fastapi import HTTPException, status
from schemas import Stock, StockUpdateInput, UserUpdateInput

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
        logger.error(f"{contextual_msg} | SQL Trace: {str(exception)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal storage operation failed to process."
        )

    def _get_password_hash(self, password: str) -> str:
        try:
            password_bytes = password.encode("utf-8")
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password_bytes, salt).decode("utf-8")
        except Exception as e:
            logger.error(f"Crypto failure during string processing: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security framework processing failure."
            )

    # --- PORTFOLIO OPERATIONS ---
    def get_portfolio(self, username: str) -> list[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, company, exchange, currency, owned, cost, username FROM portfolio WHERE username = ?;",
                    (username,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching portfolio for {username}", e)

    def get_portfolio_stock(self, symbol: str, username: str) -> dict | None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, username, company, exchange, currency, owned, cost FROM portfolio WHERE symbol = ? AND username = ?;",
                    (symbol.upper().strip(), username,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            self._handle_db_error(f"Failed fetching single stock context {symbol} for {username}", e)

    def add_stock(self, stock: Stock) -> None:
        """Inserts stock configurations directly. Relies on higher-level verification for duplicates."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO portfolio (symbol, username, company, exchange, currency, owned, cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        stock.symbol.upper().strip(),
                        stock.username,
                        stock.company,
                        stock.exchange,
                        stock.currency.upper().strip(),
                        stock.owned,
                        stock.cost,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            self._handle_db_error(f"Database insertion crash for stock={stock.symbol}, user={stock.username}", e)

    def update_stock(self, symbol: str, username: str, update_data: StockUpdateInput) -> None:
        fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
        
        
        if not fields:
            raise self.create_db_exception(
                "No fields provided for update.", status.HTTP_400_BAD_REQUEST
            )

        if "currency" in fields:
            fields["currency"] = fields["currency"].upper()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clause = ", ".join([f"{key} = ?" for key in fields.keys()])
                values = list(fields.values()) + [symbol.upper()] + [username]
                
                cursor.execute(
                    f"UPDATE portfolio SET {set_clause} WHERE symbol = ? AND username = ?;", values,
                )

                if cursor.rowcount == 0:
                    raise self.create_db_exception(
                        f"Stock details not found for '{symbol}' in the Portfolio for {username}.",
                        status.HTTP_404_NOT_FOUND,
                    )

                conn.commit()

        except sqlite3.Error as e:
             self._handle_db_error(f"Database modification crash for stock={symbol}, user={username}", e)


    def delete_stock(self, symbol: str, username: str) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM portfolio WHERE symbol = ? and username = ?;", (symbol.upper(), username,))

                conn.commit()
        except sqlite3.Error as e:
            raise self._handle_db_error(f"Database removal task failed for stock={symbol}, user={username}", e)


    def register_user(self, username: str, password: str) -> dict:
        """Validates availability and registers a new user securely into SQLite."""
        hashed_password = self._get_password_hash(password)
        # Store scopes as a simple comma-separated string for SQLite simplicity
        scopes_str = "user"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, hashed_password, scopes) VALUES (?, ?, ?)",
                    (username, hashed_password, scopes_str),
                )
                conn.commit()
        except sqlite3.IntegrityError as e:
            # Triggered if the username already exists due to PRIMARY KEY constraint
            raise self._handle_db_error(f"The User '{username}' is already registered.", e)


    def delete_user(self, username: str) -> None:
        """Deletes a user from SQLite."""

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
                if cursor.rowcount == 0:
                    raise self.create_db_exception(
                        f"Could not delete User '{username}': Not Found.",
                        status.HTTP_404_NOT_FOUND,
                    )

                conn.commit()
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
