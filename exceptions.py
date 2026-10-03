class StockNotFoundException(Exception):
    def __init__(self, symbol: str,):
        self.symbol = symbol

class StockInfoNotFoundException(Exception):
    def __init__(self, symbol: str, username: str,):
        self.symbol = symbol
        self.username = username


class PortfolioException(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
