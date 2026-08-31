"""
Donchian Channel (55, 5-min) breakout screener - Streamlit app.

Shows two columns:
  CALL  -> latest 5-min close broke ABOVE the 55-period Donchian upper band
  PUT   -> latest 5-min close broke BELOW the 55-period Donchian lower band

Data source: Upstox API v3 (intraday + historical candles, stitched together).

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Deploy: push this folder to a GitHub repo, then deploy on
https://share.streamlit.io (Streamlit Community Cloud), pointing it at app.py.
Set your Upstox access token as a Streamlit secret (see README.md) rather
than hardcoding it.
"""

import time

import pandas as pd
import streamlit as st

from nifty200 import Nifty200FetchError, fetch_nifty200
from upstox_data import (
    UpstoxAPIError,
    donchian_breakout_signal,
    fetch_intraday_candles,
    fetch_previous_close,
    get_day_open,
    get_recent_candles,
    passes_gap_filter,
)

st.set_page_config(page_title="Donchian(55) 5-min Screener", layout="wide")

DEFAULT_DC_LENGTH = 55
DEFAULT_INTERVAL_MIN = 5
DEFAULT_GAP_MIN = 3.0
DEFAULT_GAP_MAX = 5.0
FALLBACK_WATCHLIST_PATH = "watchlist.csv"  # used only if the live NSE fetch fails


@st.cache_data(ttl=86400, show_spinner=False)  # Nifty 200 rebalances rarely; refresh at most daily
def load_nifty200_cached() -> pd.DataFrame:
    return fetch_nifty200()


def get_watchlist() -> pd.DataFrame:
    """Nifty 200 constituents, auto-fetched from NSE and mapped to Upstox
    instrument keys. Falls back to the bundled watchlist.csv only if the
    live fetch fails (e.g. NSE temporarily blocking the request)."""
    try:
        return load_nifty200_cached()
    except Nifty200FetchError as e:
        st.warning(
            f"Couldn't fetch the live Nifty 200 list from NSE ({e}). "
            f"Using the bundled fallback watchlist instead."
        )
        return pd.read_csv(FALLBACK_WATCHLIST_PATH)


def get_access_token() -> str:
    # Prefer Streamlit secrets (safe for deployed apps); fall back to sidebar input.
    token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "") if hasattr(st, "secrets") else ""
    with st.sidebar:
        st.subheader("Upstox Access Token")
        token_input = st.text_input(
            "Paste token (overrides secrets.toml)",
            value="",
            type="password",
            help="Upstox access tokens expire daily. Generate a fresh one each trading day.",
        )
    return token_input.strip() or token


def run_screener(
    watchlist: pd.DataFrame,
    access_token: str,
    dc_length: int,
    interval_minutes: int,
    gap_min: float,
    gap_max: float,
):
    calls, puts, errors = [], [], []
    progress = st.progress(0.0, text="Scanning...")
    total = len(watchlist)

    for i, row in enumerate(watchlist.itertuples(index=False)):
        symbol = getattr(row, "symbol")
        instrument_key = getattr(row, "instrument_key")
        try:
            intraday_df = fetch_intraday_candles(instrument_key, access_token, interval_minutes)
            day_open = get_day_open(intraday_df)

            combined_df = get_recent_candles(
                instrument_key, access_token,
                interval_minutes=interval_minutes,
                min_candles_needed=dc_length + 1,
                intraday_df=intraday_df,
            )
            result = donchian_breakout_signal(combined_df, dc_length=dc_length)

            if result is None:
                errors.append({"symbol": symbol, "reason": "Not enough candle history yet"})
                progress.progress((i + 1) / total, text=f"Scanning... {symbol}")
                continue
            if result["signal"] is None:
                progress.progress((i + 1) / total, text=f"Scanning... {symbol}")
                continue

            prev_close = fetch_previous_close(instrument_key, access_token)
            if not passes_gap_filter(result["signal"], day_open, prev_close, gap_min, gap_max):
                progress.progress((i + 1) / total, text=f"Scanning... {symbol}")
                continue

            gap = (day_open - prev_close) if result["signal"] == "CALL" else (prev_close - day_open)
            row_out = {
                "Symbol": symbol, "Close": round(result["close"], 2),
                "Open": round(day_open, 2), "Prev Close": round(prev_close, 2),
                "Gap": round(gap, 2),
                "Candle": result["candle_time"].strftime("%H:%M"),
            }
            if result["signal"] == "CALL":
                row_out["Upper DC"] = round(result["upper_dc"], 2)
                calls.append(row_out)
            else:
                row_out["Lower DC"] = round(result["lower_dc"], 2)
                puts.append(row_out)
        except UpstoxAPIError as e:
            errors.append({"symbol": symbol, "reason": str(e)})
        progress.progress((i + 1) / total, text=f"Scanning... {symbol}")

    progress.empty()
    return pd.DataFrame(calls), pd.DataFrame(puts), pd.DataFrame(errors)


def main():
    st.title("📊 Donchian Channel Breakout Screener")
    st.caption(f"DC length: {DEFAULT_DC_LENGTH} · Timeframe: {DEFAULT_INTERVAL_MIN} min · Data: Upstox API")

    access_token = get_access_token()

    with st.sidebar:
        dc_length = st.number_input("Donchian length", min_value=5, max_value=200, value=DEFAULT_DC_LENGTH)
        interval_minutes = st.number_input("Candle interval (min)", min_value=1, max_value=60, value=DEFAULT_INTERVAL_MIN)
        st.markdown("**Gap filter (vs previous day's close)**")
        gap_col1, gap_col2 = st.columns(2)
        with gap_col1:
            gap_min = st.number_input("Min ₹ gap", min_value=0.0, value=DEFAULT_GAP_MIN, step=0.5)
        with gap_col2:
            gap_max = st.number_input("Max ₹ gap", min_value=0.0, value=DEFAULT_GAP_MAX, step=0.5)
        st.caption("CALL needs open ₹ gap-up vs prev close; PUT needs open ₹ gap-down vs prev close, both within this range.")
        if st.button("🔄 Refresh Nifty 200 list"):
            load_nifty200_cached.clear()
        run_clicked = st.button("🔍 Run Screener", type="primary", use_container_width=True)

    watchlist = get_watchlist()
    st.sidebar.caption(f"Universe: Nifty 200 · {len(watchlist)} symbols loaded (auto-fetched from NSE)")

    if not access_token:
        st.warning("Enter your Upstox access token in the sidebar to run the screener.")
        st.dataframe(watchlist, use_container_width=True)
        return

    if run_clicked:
        st.session_state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        calls_df, puts_df, errors_df = run_screener(
            watchlist, access_token, dc_length, interval_minutes, gap_min, gap_max
        )
        st.session_state["calls_df"] = calls_df
        st.session_state["puts_df"] = puts_df
        st.session_state["errors_df"] = errors_df

    if "calls_df" in st.session_state:
        st.caption(f"Last run: {st.session_state.get('last_run', '')}")
        col_call, col_put = st.columns(2)

        with col_call:
            st.subheader(f"🟢 CALL — broke above DC({dc_length})")
            df = st.session_state["calls_df"]
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No call breakouts.")

        with col_put:
            st.subheader(f"🔴 PUT — broke below DC({dc_length})")
            df = st.session_state["puts_df"]
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No put breakdowns.")

        errors_df = st.session_state["errors_df"]
        if not errors_df.empty:
            with st.expander(f"⚠️ {len(errors_df)} symbol(s) skipped / errored"):
                st.dataframe(errors_df, use_container_width=True, hide_index=True)
    else:
        st.info("Click **Run Screener** in the sidebar to scan your watchlist.")
        st.dataframe(watchlist, use_container_width=True)


if __name__ == "__main__":
    main()
