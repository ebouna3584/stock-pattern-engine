"""
Sector definitions — the 11 GICS sectors via their SPDR Select Sector ETF,
plus a broad-market "Indexes" view. Each maps to a small set of representative
large-cap constituents so a sector view stays fast (~6 tickers fetched+analyzed
per request) rather than scanning the whole sector.
"""

SECTORS = {
    "technology": {
        "name": "Technology",
        "etf": "XLK",
        "stocks": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL"],
    },
    "financials": {
        "name": "Financials",
        "etf": "XLF",
        "stocks": ["JPM", "BAC", "WFC", "GS", "MS"],
    },
    "healthcare": {
        "name": "Health Care",
        "etf": "XLV",
        "stocks": ["UNH", "JNJ", "LLY", "ABBV", "MRK"],
    },
    "energy": {
        "name": "Energy",
        "etf": "XLE",
        "stocks": ["XOM", "CVX", "COP", "SLB", "EOG"],
    },
    "consumer_discretionary": {
        "name": "Consumer Discretionary",
        "etf": "XLY",
        "stocks": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    },
    "consumer_staples": {
        "name": "Consumer Staples",
        "etf": "XLP",
        "stocks": ["PG", "KO", "PEP", "WMT", "COST"],
    },
    "industrials": {
        "name": "Industrials",
        "etf": "XLI",
        "stocks": ["CAT", "BA", "HON", "UPS", "GE"],
    },
    "materials": {
        "name": "Materials",
        "etf": "XLB",
        "stocks": ["LIN", "SHW", "APD", "FCX", "NEM"],
    },
    "utilities": {
        "name": "Utilities",
        "etf": "XLU",
        "stocks": ["NEE", "DUK", "SO", "D", "AEP"],
    },
    "real_estate": {
        "name": "Real Estate",
        "etf": "XLRE",
        "stocks": ["PLD", "AMT", "EQIX", "SPG", "O"],
    },
    "communication_services": {
        "name": "Communication Services",
        "etf": "XLC",
        "stocks": ["GOOGL", "META", "NFLX", "DIS", "VZ"],
    },
    "indexes": {
        "name": "Broad Market Indexes",
        "etf": "SPY",
        "stocks": ["QQQ", "DIA", "IWM", "VTI"],
    },
}


def list_sectors() -> list:
    return [
        {"key": key, "name": v["name"], "etf": v["etf"]}
        for key, v in SECTORS.items()
    ]


def get_sector(key: str) -> dict:
    return SECTORS.get(key)
