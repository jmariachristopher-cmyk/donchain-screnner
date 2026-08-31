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

from upstox_data import UpstoxAPIError, donchian_breakout_signal, get_recent_candles

st.set_page_config(page_title="Donchian(55) 5-min Screener", layout="wide")

DEFAULT_DC_LENGTH = 55
DEFAULT_INTERVAL_MIN = 5


@st.cache_data(ttl=60, show_spinner=False)
def load_watchlist(path: str = "watchlist.csv") -> pd.DataFrame:
    return pd.read_csv(path)


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


def run_screener(watchlist: pd.DataFrame, access_token: str, dc_length: int, interval_minutes: int):
    calls, puts, errors = [], [], []
    progress = st.progress(0.0, text="Scanning...")
    total = len(watchlist)

    for i, row in enumerate(watchlist.itertuples(index=False)):
        symbol = getattr(row, "symbol")
        instrument_key = getattr(row, "instrument_key")
        try:
            df = get_recent_candles(
                instrument_key, access_token,
                interval_minutes=interval_minutes,
                min_candles_needed=dc_length + 1,
            )
            result = donchian_breakout_signal(df, dc_length=dc_length)
            if result is None:
                errors.append({"symbol": symbol, "reason": "Not enough candle history yet"})
            elif result["signal"] == "CALL":
                calls.append({
                    "Symbol": symbol, "Close": round(result["close"], 2),
                    "Upper DC": round(result["upper_dc"], 2),
                    "Candle": result["candle_time"].strftime("%H:%M"),
                })
            elif result["signal"] == "PUT":
                puts.append({
                    "Symbol": symbol, "Close": round(result["close"], 2),
                    "Lower DC": round(result["lower_dc"], 2),
                    "Candle": result["candle_time"].strftime("%H:%M"),
                })
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
        watchlist_file = st.file_uploader("Watchlist CSV (symbol, instrument_key)", type="csv")
        run_clicked = st.button("🔍 Run Screener", type="primary", use_container_width=True)
        st.caption("CSV format: two columns — `symbol`, `instrument_key` (e.g. NSE_EQ|INE002A01018)")

    watchlist = pd.read_csv(watchlist_file) if watchlist_file else load_watchlist()

    if not access_token:
        st.warning("Enter your Upstox access token in the sidebar to run the screener.")
        st.dataframe(watchlist, use_container_width=True)
        return

    if run_clicked:
        st.session_state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        calls_df, puts_df, errors_df = run_screener(watchlist, access_token, dc_length, interval_minutes)
        st.session_state["calls_df"] = calls_df
        st.session_state["puts_df"] = puts_df
        st.session_state["errors_df"] = errors_df

    if "calls_df" in st.session_state:
        st.caption(f"Last run: {st.session_state.get('last_run', '')}")
        col_call, col_put = st.columns(2)

        with col_call:
            st.subheader(f"🟢 CALL — broke above DC({dc_length})")
            df = st.session_state["calls_df"]
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No call breakouts.")

        with col_put:
            st.subheader(f"🔴 PUT — broke below DC({dc_length})")
            df = st.session_state["puts_df"]
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No put breakdowns.")

        errors_df = st.session_state["errors_df"]
        if not errors_df.empty:
            with st.expander(f"⚠️ {len(errors_df)} symbol(s) skipped / errored"):
                st.dataframe(errors_df, use_container_width=True, hide_index=True)
    else:
        st.info("Click **Run Screener** in the sidebar to scan your watchlist.")
        st.dataframe(watchlist, use_container_width=True)


if __name__ == "__main__":
    main()
