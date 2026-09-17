import bcrypt  # Use native bcrypt directly
import logging
import sqlite3
from fastapi import HTTPException, status
from schemas import StockInput, StockUpdateInput, UserUpdateInput

# Setup standard structured logging instead of using print()
logger = logging.getLogger("portfolio_app")


class DatabaseService:
    def __init__(self):
        self.db_path = "/home/alanfryer/sqlite/portfolio.db"

        logger.info("Intialized the Database Service")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_password_hash(self, password: str) -> str:
        """Hashes a plain text password safely using native bcrypt."""
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed_bytes = bcrypt.hashpw(password_bytes, salt)
        return hashed_bytes.decode("utf-8")

    # --- PORTFOLIO OPERATIONS ---
    def get_portfolio(self) -> list[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, company, exchange, currency, owned, cost FROM portfolio;"
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

    def get_portfolio_stock(self, symbol: str) -> dict | None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, company, exchange, currency, owned, cost FROM portfolio WHERE symbol = ?;",
                    (symbol.upper(),),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

    def add_stock(self, stock: StockInput) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol FROM portfolio WHERE symbol = ?;",
                    (stock.symbol.upper(),),
                )

                if cursor.fetchone():
                    raise self.create_db_exception(
                        f"Stock symbol '{stock.symbol.upper()}' already exists.",
                        status.HTTP_400_BAD_REQUEST,
                    )

                cursor.execute(
                    """
                    INSERT INTO portfolio (symbol, company, exchange, currency, owned, cost)
                    VALUES (?, ?, ?, ?, ?, ?);
                """,
                    (
                        stock.symbol.upper(),
                        stock.company,
                        stock.exchange,
                        stock.currency.upper(),
                        stock.owned,
                        stock.cost,
                    ),
                )

                conn.commit()

        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

        return {
            "message": "The Stock for '{stock.company}' has been added to the Portfolio."
        }

    def update_stock(self, symbol: str, update_data: StockUpdateInput) -> None:
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
                values = list(fields.values()) + [symbol.upper()]

                cursor.execute(
                    f"UPDATE portfolio SET {set_clause} WHERE symbol = ?;", values
                )

                if cursor.rowcount == 0:
                    raise self.create_db_exception(
                        f"Stock details not found for '{symbol}'.",
                        status.HTTP_404_NOT_FOUND,
                    )

                conn.commit()

        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

        return {"message": "The Stock for '{symbol}' has been updated."}

    def delete_stock(self, symbol: str) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE symbol = ?;", (symbol.upper(),))

                if cursor.rowcount == 0:
                    raise self.create_db_exception(
                        f"Stock details not found for '{symbol}'.",
                        status.HTTP_404_NOT_FOUND,
                    )

                conn.commit()
        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

        return {"message": "The Stock for '{symbol}' has been added to the Portfolio."}

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
            raise self.create_db_exception(
                f"The User '{username}' is already registered: {e}",
                status.HTTP_400_BAD_REQUEST,
            )

        return {
            "message": "The User '{username}' has been registered with the Portfolio."
        }

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
            raise self.create_db_exception(f"Database error: {e}")

        return {"message": f"The Portfolio User '{username}' has been Deleted."}

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

    def create_db_exception(
        self, detail: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ) -> HTTPException:
        """
        Factory function to standardise and build HTTPExceptions.
        """

        logger.error(detail)

        return HTTPException(status_code=status_code, detail=detail)

    def update_user_password(self, username: str, update_data: UserUpdateInput) -> dict:
        """Hashes and updates a user's password securely in SQLite."""
        # Ensure password is provided in the update payload
        if not update_data.password:
            raise self.create_db_exception(
                "Password field is required for update.", status.HTTP_400_BAD_REQUEST
            )

        hashed_password = self._get_password_hash(update_data.password)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET hashed_password = ? WHERE username = ?;",
                    (hashed_password, username),
                )

                if cursor.rowcount == 0:
                    raise self.create_db_exception(
                        f"User '{username}' not found.", status.HTTP_404_NOT_FOUND
                    )

                conn.commit()

        except sqlite3.Error as e:
            raise self.create_db_exception(f"Database error: {e}")

        return {
            "username": username,
            "message": f"Password for user '{username}' has been updated successfully.",
        }
