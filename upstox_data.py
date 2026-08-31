"""
Upstox v3 API helpers for the Donchian Channel screener.

Endpoints used (Upstox Historical Candle Data V3 / Intraday Candle Data V3):
  Intraday (today, still forming):
    GET https://api.upstox.com/v3/historical-candle/intraday/{instrument_key}/minutes/{interval}
  Historical (completed days):
    GET https://api.upstox.com/v3/historical-candle/{instrument_key}/minutes/{interval}/{to_date}/{from_date}

Candle response rows are: [timestamp, open, high, low, close, volume, open_interest]
and are returned NEWEST FIRST.

Docs: https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/
      https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
"""

import datetime as dt
from urllib.parse import quote

import pandas as pd
import requests

BASE_URL = "https://api.upstox.com/v3/historical-candle"
INTERVAL_UNIT = "minutes"
REQUEST_TIMEOUT = 10


class UpstoxAPIError(Exception):
    pass


def _headers(access_token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }


def _candles_to_df(candles: list) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    # API returns newest-first; sort ascending (oldest -> newest) for indicator math
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_intraday_candles(instrument_key: str, access_token: str, interval_minutes: int = 5) -> pd.DataFrame:
    """Today's candles (may be incomplete / short list before market has run long)."""
    url = f"{BASE_URL}/intraday/{quote(instrument_key, safe='')}/{INTERVAL_UNIT}/{interval_minutes}"
    resp = requests.get(url, headers=_headers(access_token), timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise UpstoxAPIError(f"{instrument_key}: intraday fetch failed ({resp.status_code}) {resp.text[:200]}")
    data = resp.json()
    return _candles_to_df(data.get("data", {}).get("candles", []))


def fetch_historical_candles(
    instrument_key: str,
    access_token: str,
    interval_minutes: int = 5,
    lookback_days: int = 7,
) -> pd.DataFrame:
    """Prior completed days' candles, used to pad history for the Donchian window
    early in the trading session when today alone doesn't have enough candles yet."""
    to_date = dt.date.today().isoformat()
    from_date = (dt.date.today() - dt.timedelta(days=lookback_days)).isoformat()
    url = (
        f"{BASE_URL}/{quote(instrument_key, safe='')}/{INTERVAL_UNIT}/{interval_minutes}"
        f"/{to_date}/{from_date}"
    )
    resp = requests.get(url, headers=_headers(access_token), timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise UpstoxAPIError(f"{instrument_key}: historical fetch failed ({resp.status_code}) {resp.text[:200]}")
    data = resp.json()
    return _candles_to_df(data.get("data", {}).get("candles", []))


def get_recent_candles(
    instrument_key: str,
    access_token: str,
    interval_minutes: int = 5,
    min_candles_needed: int = 56,
) -> pd.DataFrame:
    """Combine historical + intraday candles into one ascending-time series with
    at least `min_candles_needed` rows where possible, deduplicated on timestamp."""
    intraday_df = fetch_intraday_candles(instrument_key, access_token, interval_minutes)

    combined = intraday_df
    if len(combined) < min_candles_needed:
        hist_df = fetch_historical_candles(instrument_key, access_token, interval_minutes)
        combined = pd.concat([hist_df, intraday_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    return combined


def donchian_breakout_signal(df: pd.DataFrame, dc_length: int = 55) -> dict:
    """
    Compute the Donchian Channel from the `dc_length` candles BEFORE the latest
    candle (so the latest close is checked against a channel it wasn't part of
    -- avoids lookahead / the channel silently including the breakout bar itself).

    Returns a dict with signal ('CALL' / 'PUT' / None), latest close, and the
    channel bounds, or None if there isn't enough history yet.
    """
    if len(df) < dc_length + 1:
        return None

    window = df.iloc[-(dc_length + 1):-1]  # the dc_length candles strictly before the latest one
    latest = df.iloc[-1]

    upper = window["high"].max()
    lower = window["low"].min()
    close = latest["close"]

    if close > upper:
        signal = "CALL"
    elif close < lower:
        signal = "PUT"
    else:
        signal = None

    return {
        "signal": signal,
        "close": close,
        "upper_dc": upper,
        "lower_dc": lower,
        "candle_time": latest["timestamp"],
    }
