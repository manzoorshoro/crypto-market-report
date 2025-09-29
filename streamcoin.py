# streamcoin.py
import requests
import pandas as pd
from datetime import datetime, timezone
from dateutil import tz
import streamlit as st

# =========================== CONFIG ===========================
TOP_N = 50
PER_PAGE = 250
VS_CCY = "usd"

# Exclusions (wrapped & stables)
INCLUDE_ONLY = []  # keep empty to auto-pick top coins
EXCLUDE_IDS = {"wrapped-bitcoin", "weth", "staked-ether", "wrapped-beacon-eth", "coinbase-wrapped-staked-eth"}
EXCLUDE_SYMS = {"wbtc", "weth", "steth", "wbeth", "cbeth"}
KNOWN_STABLE_IDS = {
    "tether","usd-coin","dai","frax","first-digital-usd","true-usd","paxos-standard",
    "binance-usd","gemini-dollar","liquity-usd","usdd","nusd","susd","usde","paypal-usd"
}
KNOWN_STABLE_SYMS = {
    "usdt","usdc","dai","frax","fdusd","tusd","usdp","busd","gusd","lusd","usdd","susd","usde","pyusd"
}

CG_BASE = "https://api.coingecko.com/api/v3"

# Optional future scenario overrides (static text, not live data)
SCENARIO_OVERRIDES = {
    "bitcoin":      ("200000", "120000–150000", "80000–100000"),
    "ethereum":     ("10000",  "5000–7000",     "2500–4000"),
    "solana":       ("800",    "200–400",       "<150"),
    "binancecoin":  ("2000",   "1000–1300",     "500–800"),
    "ripple":       ("10",     "3–5",           "1.5–3"),
    "cardano":      ("4",      "1–2",           "0.3–0.8"),
    "dogecoin":     ("1.00",   "0.30–0.50",     "0.10–0.25"),
    "avalanche-2":  ("150",    "40–80",         "20–35"),
    "polkadot":     ("20",     "7–12",          "3–5"),
    "chainlink":    ("80",     "30–60",         "15–25"),
    "tron":         ("0.80",   "0.40–0.60",     "0.20–0.30"),
    "cosmos":       ("25",     "8–15",          "3–6"),
}

# =========================== HELPERS ===========================
def looks_stable_like(price, ch24, ch7d):
    if price is None:
        return False
    near_one = 0.95 <= price <= 1.05
    low_vol = True
    try:
        if ch24 is not None and ch7d is not None:
            low_vol = abs(ch24) < 2.5 and abs(ch7d) < 4.0
    except Exception:
        pass
    return near_one and low_vol

def default_scenarios(curr_price):
    if curr_price is None or curr_price <= 0:
        return ("—","—","—")
    bull = f"{curr_price*2.5:,.2f}"
    base = f"{curr_price*1.5:,.2f}"
    bear = f"{curr_price*0.6:,.2f}"
    return (bull, base, bear)

def cg_get_markets(vs="usd", per_page=250, page=1):
    url = f"{CG_BASE}/coins/markets"
    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "price_change_percentage": "24h,7d",
        "sparkline": "false",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def pick_universe():
    # Optionally support INCLUDE_ONLY
    if INCLUDE_ONLY:
        markets = {}
        page = 1
        while len(markets) < len(INCLUDE_ONLY) and page <= 4:
            for c in cg_get_markets(vs=VS_CCY, per_page=PER_PAGE, page=page):
                markets[c["id"]] = c
            page += 1
        return [markets[i] for i in INCLUDE_ONLY if i in markets]

    markets = cg_get_markets(vs=VS_CCY, per_page=PER_PAGE, page=1)
    markets.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)

    picked = []
    for c in markets[:TOP_N*2]:  # grab extra to allow removals
        cid = c.get("id","")
        sym = (c.get("symbol") or "").lower()
        name = (c.get("name") or "").lower()
        price = c.get("current_price")
        ch24  = c.get("price_change_percentage_24h")
        ch7d  = c.get("price_change_percentage_7d_in_currency")

        if cid in EXCLUDE_IDS or sym in EXCLUDE_SYMS:          continue
        if cid in KNOWN_STABLE_IDS or sym in KNOWN_STABLE_SYMS: continue
        if looks_stable_like(price, ch24, ch7d) and ("usd" in sym or "usd" in name):
            continue

        picked.append(c)
        if len(picked) >= TOP_N:
            break
    return picked

# =========================== DATA (CACHED) ===========================
@st.cache_data(ttl=60)  # cache for up to 60 seconds unless user presses Refresh
def fetch_data():
    universe = pick_universe()
    rows = []
    for i, c in enumerate(universe, 1):
        cid    = c.get("id")
        name   = c.get("name")
        sym    = (c.get("symbol") or "").upper()
        price  = c.get("current_price")
        ch24   = c.get("price_change_percentage_24h")
        mcap   = c.get("market_cap")

        bull, base, bear = SCENARIO_OVERRIDES.get(cid, default_scenarios(price))

        rows.append({
            "Rank": i,
            "Sym": sym,
            "Name": name,
            "Live USD": price,
            "24h %": ch24,
            "Market Cap": mcap,
            "2026 Bull": bull,
            "2026 Base": base,
            "2026 Bear": bear,
        })
    df = pd.DataFrame(rows).sort_values("Rank")
    return df

# =========================== UI ===========================
st.set_page_config(page_title="Crypto Market Report", layout="wide")
st.title("📊 Auto Crypto Market Report (Live Prices)")

# Refresh button (fixed for Streamlit >=1.30)
if st.button("🔄 Refresh Data"):
    try:
        st.cache_data.clear()   # ensure fresh API calls
    except Exception:
        pass
    st.rerun()

# Timestamp (PKT)
pk_tz = tz.gettz("Asia/Karachi")
now_str = datetime.now(timezone.utc).astimezone(pk_tz).strftime("%Y-%m-%d %H:%M %Z")
st.caption(f"Last updated: {now_str}")

# Fetch + show
try:
    df = fetch_data()
except Exception as e:
    st.error(f"Failed to fetch data from CoinGecko: {e}")
    st.stop()

# Pretty formatting for display
def fmt_price(x):
    if pd.isna(x): return "—"
    ax = abs(x)
    if ax >= 100:        return f"${x:,.2f}"
    elif ax >= 1:        return f"${x:,.4f}"
    elif ax >= 0.01:     return f"${x:,.6f}"
    elif ax >= 0.000001: return f"${x:,.8f}"
    else:                return f"${x:.2e}"

df_display = df.copy()
df_display["Live USD"]  = df_display["Live USD"].map(lambda x: fmt_price(x) if pd.notna(x) else "—")
df_display["24h %"]     = df_display["24h %"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "—")
df_display["Market Cap"]= df_display["Market Cap"].map(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")

st.dataframe(df_display, use_container_width=True)
