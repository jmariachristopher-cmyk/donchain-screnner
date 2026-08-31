"""
Fetches the current Nifty 200 constituent list from NSE and maps each stock
to its Upstox instrument_key.

Upstox instrument keys for NSE equities follow the fixed pattern
`NSE_EQ|<ISIN>` (confirmed in Upstox's own instrument JSON structure), so
once we have each stock's ISIN from NSE's official list we don't need to
download Upstox's full instrument master file at all.

NSE's index-constituent CSVs live at a stable archive URL pattern:
    https://archives.nseindia.com/content/indices/ind_nifty200list.csv
with columns: Company Name, Industry, Symbol, Series, ISIN Code

NSE's site blocks bare requests without a real browser User-Agent / cookies,
so we open a session against the homepage first to pick up the cookies it
expects before requesting the CSV.
"""

import io

import pandas as pd
import requests

NSE_HOMEPAGE = "https://www.nseindia.com"
NSE_NIFTY200_CSV = "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class Nifty200FetchError(Exception):
    pass


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    # NSE issues cookies on the homepage that later requests are checked against.
    session.get(NSE_HOMEPAGE, timeout=10)
    return session


def fetch_nifty200(timeout: int = 15) -> pd.DataFrame:
    """Returns columns: symbol, company_name, isin, instrument_key."""
    try:
        session = _nse_session()
        resp = session.get(NSE_NIFTY200_CSV, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise Nifty200FetchError(f"Could not reach NSE for the Nifty 200 list: {e}") from e

    try:
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(
            columns={
                "Company Name": "company_name",
                "Industry": "industry",
                "Symbol": "symbol",
                "Series": "series",
                "ISIN Code": "isin",
            }
        )
        df["isin"] = df["isin"].astype(str).str.strip()
        df["symbol"] = df["symbol"].astype(str).str.strip()
        df["instrument_key"] = "NSE_EQ|" + df["isin"]
        return df[["symbol", "company_name", "isin", "instrument_key"]].dropna(subset=["isin"])
    except Exception as e:
        raise Nifty200FetchError(f"Fetched a response but couldn't parse the Nifty 200 CSV: {e}") from e
