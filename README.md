# Donchian Channel(55) 5-min Breakout Screener

Streamlit app that scans a watchlist using Upstox market data and splits
results into two columns:

- **CALL** — latest 5-minute close broke **above** the 55-period Donchian upper band
- **PUT** — latest 5-minute close broke **below** the 55-period Donchian lower band

The Donchian channel is computed from the 55 candles **before** the latest
one, so the breakout candle isn't included in its own channel.

## 1. Get an Upstox access token

Upstox access tokens are valid for **one trading day** and must be
regenerated each morning:

1. Create an app at https://developer.upstox.com and note your `api_key` / `api_secret` and redirect URI.
2. Complete the OAuth login flow (see [Upstox Authentication docs](https://upstox.com/developer/api-documentation/authentication)) to get an `access_token`.
3. Either:
   - Paste it into the sidebar text box each time you open the app, **or**
   - Store it as a Streamlit secret (see below) if you refresh it daily.

> Consider scripting the daily OAuth login separately (Upstox supports a
> semi-automated TOTP-based login) if you want this fully hands-off — that's
> outside the scope of this screener but worth building as a companion script.

## 2. Watchlist: Nifty 200 (auto-fetched)

The app automatically pulls the current Nifty 200 constituent list from
NSE's official index CSV (`ind_nifty200list.csv`) and converts each stock's
ISIN into its Upstox instrument key (`NSE_EQ|<ISIN>` — this is Upstox's
documented, fixed key format for NSE equities, so no separate lookup
against Upstox's instrument master file is needed).

- The list is cached for 24 hours (Nifty 200 rebalances only twice a year);
  use the **"🔄 Refresh Nifty 200 list"** button in the sidebar to force a
  re-fetch.
- If NSE ever blocks the request (their site occasionally rate-limits
  requests from cloud IPs like Streamlit Cloud's), the app falls back to
  the bundled `watchlist.csv` and shows a warning — swap in your own
  symbols there if that happens repeatedly.

## 3. Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 4. Push to GitHub

```bash
git init
git add .
git commit -m "Donchian breakout screener"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.gitignore` already excludes `.streamlit/secrets.toml` so your token never
gets committed.

## 5. Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. "New app" → select your repo/branch → main file path `app.py`.
3. In **Settings → Secrets**, paste:
   ```toml
   UPSTOX_ACCESS_TOKEN = "your_todays_token"
   ```
4. Deploy. Since the token expires daily, you'll need to update this secret
   (or just paste a fresh token into the sidebar) each trading day.

## Notes / limitations

- Upstox intraday candles only cover the **current** trading day, so early
  in the session there may not be 55 five-minute candles yet. The app
  automatically pads with the prior days' historical candles until there's
  enough history — this only affects the first ~15–20 minutes after open on
  a 5-min/55-length setup (~4.5 hours of data needed).
- The screener does one API call per symbol per run — for large watchlists,
  be mindful of Upstox's rate limits.
- This is a screening tool, not a trading signal generator — always verify
  before acting on it.
