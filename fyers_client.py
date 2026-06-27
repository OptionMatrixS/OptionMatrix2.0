"""
fyers_client.py — Fyers API v3 integration for Option Matrix
Auto-TOTP token generation, symbol building, quotes, candles, Black-Scholes Greeks
"""

import streamlit as st
import requests
import hashlib
import base64
import json
import os
import re
import time
import math
import pyotp
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

try:
    from fyers_apiv3 import fyersModel
except ImportError:
    fyersModel = None

# ── Constants ────────────────────────────────────────────────────────────────

LOT_SIZES = {"NIFTY": 65, "SENSEX": 20, "BANKNIFTY": 35, "FINNIFTY": 40}

INDEX_SYMBOLS = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
}

LEG_COLORS = {
    1: "#2962ff", 2: "#26a69a", 3: "#ff9800",
    4: "#ef5350", 5: "#9c27b0", 6: "#00bcd4",
    7: "#2962ff", 8: "#26a69a", 9: "#ff9800", 10: "#ef5350",
}

MONTH_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

TOKEN_FILE = "fyers_token.json"
RISK_FREE_RATE = 0.07  # 7% annual

# ── Time Helpers ─────────────────────────────────────────────────────────────

def get_ist_now():
    """Get current IST timestamp (Streamlit Cloud runs UTC)."""
    return pd.Timestamp.now(tz="Asia/Kolkata").replace(tzinfo=None)


def is_market_open():
    """Check if Indian equity markets are currently open."""
    now = get_ist_now()
    if now.weekday() >= 5:
        return False
    mkt_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return mkt_open <= now <= mkt_close


def market_status_html():
    """Return HTML badge showing market open/closed status."""
    now = get_ist_now()
    ts = now.strftime("%H:%M:%S IST")
    if is_market_open():
        return f'<span style="color:#26a69a;">🟢 OPEN</span> <span style="color:#787b86;font-size:12px;">{ts}</span>'
    else:
        return f'<span style="color:#ef5350;">🔴 CLOSED</span> <span style="color:#787b86;font-size:12px;">{ts}</span>'


# ── Token Generation (5-step TOTP login) ─────────────────────────────────────

def _generate_token_inner():
    """
    TOTP login flow for Fyers API v3.
    Steps 1-3: TOTP authentication.
    Step 4: Use bearer to authorize app and get auth_code via redirect.
    Step 5: Validate auth_code to get final access_token.
    """
    client_id = str(st.secrets["FYERS_CLIENT_ID"])
    secret_key = str(st.secrets["FYERS_SECRET_KEY"])
    username = str(st.secrets["FYERS_USERNAME"])
    pin = str(st.secrets["FYERS_PIN"])
    totp_key = str(st.secrets["FYERS_TOTP_KEY"])
    redirect_uri = "http://127.0.0.1:8080/"

    # Step 1 — Send login OTP
    r1 = requests.post(
        "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
        json={
            "fy_id": base64.b64encode(username.encode()).decode(),
            "app_id": "2",
        },
    )
    r1.raise_for_status()
    r1d = r1.json()
    if r1d.get("code") != 200 and r1d.get("s") != "ok":
        raise RuntimeError(f"Step 1 failed: {r1d}")
    rk1 = r1d["request_key"]

    # Step 2 — Verify TOTP
    totp_code = pyotp.TOTP(totp_key).now()
    r2 = requests.post(
        "https://api-t2.fyers.in/vagator/v2/verify_otp",
        json={"request_key": rk1, "otp": totp_code},
    )
    r2.raise_for_status()
    r2d = r2.json()
    if r2d.get("code") != 200 and r2d.get("s") != "ok":
        raise RuntimeError(f"Step 2 failed (check TOTP_KEY): {r2d}")
    rk2 = r2d["request_key"]

    # Step 3 — Verify PIN
    r3 = requests.post(
        "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
        json={
            "request_key": rk2,
            "identity_type": "pin",
            "identifier": base64.b64encode(pin.encode()).decode(),
        },
    )
    r3.raise_for_status()
    r3d = r3.json()
    if "data" not in r3d or "access_token" not in r3d.get("data", {}):
        raise RuntimeError(f"Step 3 failed: {r3d}")
    bearer = r3d["data"]["access_token"]

    # Step 4 — Get auth_code via shared session (POST sets cookies, GET uses them)
    import urllib.parse
    app_id_parts = client_id.split("-")
    app_id = app_id_parts[0]
    app_type = app_id_parts[1] if len(app_id_parts) > 1 else "100"

    # Use a single session so POST response cookies carry to GET
    # Browser-like headers needed to avoid Cloudflare HTML challenge pages
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {bearer}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://api-t1.fyers.in/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    })

    # Step 4a — POST /api/v3/token (sets session cookies)
    r4a = s.post(
        "https://api-t1.fyers.in/api/v3/token",
        json={
            "fyers_id": username,
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "appType": app_type,
            "code_challenge": "",
            "state": "sample",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True,
        },
    )
    r4ad = r4a.json() if r4a.content else {}
    if r4ad.get("s") != "ok":
        raise RuntimeError(f"Step 4a failed: {r4ad}")

    # Check if Step 4a already returned auth_code directly (some API versions)
    r4a_data = r4ad.get("data", {}) if isinstance(r4ad.get("data"), dict) else {}
    # Some versions return a URL with auth_code embedded
    r4a_url = r4a_data.get("Url", r4a_data.get("url", ""))
    if r4a_url and "auth_code=" in r4a_url:
        auth_code = r4a_url.split("auth_code=")[1].split("&")[0]
        if auth_code:
            # Skip Step 4b entirely — go straight to Step 5
            session_obj = fyersModel.SessionModel(
                client_id=client_id,
                secret_key=secret_key,
                redirect_uri=redirect_uri,
                response_type="code",
                grant_type="authorization_code",
            )
            session_obj.set_token(auth_code)
            response = session_obj.generate_token()
            if isinstance(response, dict) and "access_token" in response:
                return response["access_token"]
    # Step 4b — Get auth_code and exchange for access_token
    # The generate-authcode GET endpoint returns login HTML for non-browser
    # clients, so we try multiple strategies to get the token directly.

    import hashlib as _hl
    app_hash = _hl.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()
    data_auth = r4a_data.get("auth", "")

    auth_code = ""
    strategy_errors = {}  # Capture what each strategy returned

    # ── Strategy 1: Try data.auth as the auth_code via SDK ──
    if data_auth:
        try:
            session_obj = fyersModel.SessionModel(
                client_id=client_id, secret_key=secret_key,
                redirect_uri=redirect_uri, response_type="code",
                grant_type="authorization_code",
            )
            session_obj.set_token(data_auth)
            resp1 = session_obj.generate_token()
            if isinstance(resp1, dict) and "access_token" in resp1:
                return resp1["access_token"]
            strategy_errors["s1_sdk"] = str(resp1)[:200]
        except Exception as e:
            strategy_errors["s1_sdk"] = str(e)[:200]

    # ── Strategy 2a: POST validate-authcode (api-t1) ──
    if data_auth:
        try:
            r_val = requests.post(
                "https://api-t1.fyers.in/api/v3/validate-authcode",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": app_hash,
                    "code": data_auth,
                },
            )
            r_vald = r_val.json() if r_val.content else {}
            if r_vald.get("access_token"):
                return r_vald["access_token"]
            strategy_errors["s2a_validate"] = str(r_vald)[:200]
        except Exception as e:
            strategy_errors["s2a_validate"] = str(e)[:200]

    # ── Strategy 2b: POST validate-authcode (api.fyers.in) ──
    if data_auth:
        try:
            r_val2 = requests.post(
                "https://api.fyers.in/api/v3/validate-authcode",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": app_hash,
                    "code": data_auth,
                },
            )
            r_val2d = r_val2.json() if r_val2.content else {}
            if r_val2d.get("access_token"):
                return r_val2d["access_token"]
            strategy_errors["s2b_validate_api"] = str(r_val2d)[:200]
        except Exception as e:
            strategy_errors["s2b_validate_api"] = str(e)[:200]

    # ── Strategy 3a: client_id:bearer as token ──
    try:
        test_token = f"{client_id}:{bearer}"
        test_fyers = fyersModel.FyersModel(
            client_id=client_id, is_async=False,
            token=test_token, log_path=""
        )
        test_resp = test_fyers.get_profile()
        if isinstance(test_resp, dict) and test_resp.get("code") == 200:
            return test_token
        strategy_errors["s3a_bearer"] = str(test_resp)[:200]
    except Exception as e:
        strategy_errors["s3a_bearer"] = str(e)[:200]

    # ── Strategy 3b: client_id:data_auth as token ──
    if data_auth:
        try:
            test_token2 = f"{client_id}:{data_auth}"
            test_fyers2 = fyersModel.FyersModel(
                client_id=client_id, is_async=False,
                token=test_token2, log_path=""
            )
            test_resp2 = test_fyers2.get_profile()
            if isinstance(test_resp2, dict) and test_resp2.get("code") == 200:
                return test_token2
            strategy_errors["s3b_data_auth"] = str(test_resp2)[:200]
        except Exception as e:
            strategy_errors["s3b_data_auth"] = str(e)[:200]

    # ── Strategy 4: GET generate-authcode with cookie (legacy fallback) ──
    if data_auth:
        s.cookies.set("FYERS_TOKEN", data_auth, domain=".fyers.in", path="/")

    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&state=sample"
    )

    def _extract_auth_code(text):
        if not text:
            return ""
        m = re.search(r'auth_code=([a-zA-Z0-9_\-]+)', text)
        if m:
            return m.group(1)
        m = re.search(r'"auth_code"\s*:\s*"([^"]+)"', text)
        if m:
            return m.group(1)
        return ""

    r4b = s.get(auth_url, allow_redirects=False)
    if r4b.status_code in (301, 302, 303, 307, 308):
        auth_code = _extract_auth_code(r4b.headers.get("Location", ""))
    if not auth_code:
        auth_code = _extract_auth_code(r4b.text if hasattr(r4b, 'text') else "")
    if not auth_code:
        r4c = s.get(auth_url, allow_redirects=True)
        auth_code = _extract_auth_code(str(r4c.url))
        if not auth_code:
            auth_code = _extract_auth_code(r4c.text if hasattr(r4c, 'text') else "")

    if not auth_code:
        raise RuntimeError(
            f"All strategies failed. "
            f"strategy_results={json.dumps(strategy_errors)}"
        )

    # Step 5 — Validate auth_code → access_token
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )
    session.set_token(auth_code)
    response = session.generate_token()
    if isinstance(response, dict) and "access_token" in response:
        return response["access_token"]

    raise RuntimeError(f"Step 5 failed: {response}")


@st.cache_resource(ttl=43200)  # 12 hours — generates once, shared across ALL sessions
def _get_cached_token(_date_key):
    """
    Generate and cache token globally. The _date_key param ensures
    a new token is generated each day. Raises on failure so
    st.cache_resource never caches an error.
    """
    # Retry with backoff for 429 rate limiting
    max_retries = 3
    for attempt in range(max_retries):
        try:
            token = _generate_token_inner()
            return token
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = (attempt + 1) * 10  # 10s, 20s, 30s
                time.sleep(wait)
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Fyers API rate limited (429) after {max_retries} retries. "
                        f"Wait a few minutes and refresh the page."
                    ) from e
            else:
                raise
        except Exception:
            raise
    raise RuntimeError("Token generation failed after retries.")


def get_fyers_client():
    """
    Get or create Fyers API client.
    Token cached globally via @st.cache_resource (one generation per day).
    Client instance cached in session_state['_fc'] per session.
    """
    _SS = st.session_state
    if "_fc" in _SS and _SS["_fc"] is not None:
        return _SS["_fc"]

    # Use today's date as cache key — new token each day
    today_str = date.today().isoformat()
    token = _get_cached_token(today_str)

    client_id = str(st.secrets["FYERS_CLIENT_ID"])
    fyers = fyersModel.FyersModel(
        client_id=client_id, is_async=False, token=token, log_path=""
    )
    _SS["_fc"] = fyers
    return fyers


def refresh_token():
    """Force regenerate token (clears global cache)."""
    _SS = st.session_state
    _SS.pop("_fc", None)
    _get_cached_token.clear()  # clear @st.cache_resource cache
    return get_fyers_client()


# ── Symbol Building ──────────────────────────────────────────────────────────

def _label_to_code(label, index="NIFTY"):
    """
    Convert Fyers expiry label to symbol code.
    '19 MAY 26 (W)' → '260519'  (weekly: YYMMDD, MM has no leading zero → '26519')
    '29 MAY 26 (M)' → '26MAY'   (monthly: YYMON)
    Always parses label directly as fallback — never relies solely on session state.
    """
    _SS = st.session_state
    cache_key = f"lc_{index}_{label}"

    # Check cache first
    if cache_key in _SS and _SS[cache_key]:
        return _SS[cache_key]

    # Direct parse
    code = _parse_label(label)
    if code:
        _SS[cache_key] = code
    return code or label.strip()


def _parse_label(label):
    """Parse expiry label string directly using regex."""
    try:
        label = label.strip()
        m = re.match(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{2})\s*\(([WM])\)", label)
        if not m:
            return None
        dd, mon, yy, wm = m.groups()
        if wm == "M":
            return f"{yy}{mon}"
        else:
            mm = str(MONTH_NUM.get(mon, 0))  # No leading zero
            return f"{yy}{mm}{dd.zfill(2)}"
    except Exception:
        return None


def build_symbol(index, code, opt_type, strike):
    """
    Build Fyers option symbol.
    Weekly:  NSE:NIFTY26519CE23750  (code=260519 → 26+5+19)
    Monthly: NSE:NIFTY26MAYCE23000  (code=26MAY)
    """
    exchange = "BSE" if index in ("SENSEX", "BANKEX") else "NSE"
    strike_str = str(int(float(str(strike).replace(",", ""))))

    if any(c.isalpha() for c in str(code)):
        # Monthly format
        return f"{exchange}:{index}{code}{opt_type}{strike_str}"
    else:
        # Weekly format: code = YYMMDD → YY + M(no leading zero) + DD
        code = str(code)
        yy = code[:2]
        mm = str(int(code[2:4]))  # strip leading zero
        dd = code[4:6]
        return f"{exchange}:{index}{yy}{mm}{dd}{opt_type}{strike_str}"


def build_symbol_from_label(index, expiry_label, opt_type, strike):
    """Convenience: label → code → symbol."""
    code = _label_to_code(expiry_label, index)
    return build_symbol(index, code, opt_type, strike)


# ── Option Chain, Expiries, Strikes ─────────────────────────────────────────

def get_option_chain(index):
    """Fetch full option chain. Returns raw response dict."""
    try:
        fyers = get_fyers_client()
        idx_sym = INDEX_SYMBOLS.get(index, f"NSE:{index}-INDEX")
        resp = fyers.optionchain(
            data={"symbol": idx_sym, "strikecount": 0, "timestamp": ""}
        )
        if resp.get("code") != 200:
            raise RuntimeError(f"Option chain error: {resp}")
        return resp
    except Exception as e:
        raise RuntimeError(f"Option chain fetch failed: {e}")


def get_expiries(index):
    """Get sorted expiry labels for an index. Cached in session state."""
    _SS = st.session_state
    key = f"exp_{index}"
    if key in _SS and _SS[key]:
        return _SS[key]

    try:
        resp = get_option_chain(index)
        seen = set()
        expiries = []
        for opt in resp.get("data", {}).get("optionsChain", []):
            lbl = opt.get("expiryDate", "")
            if lbl and lbl not in seen:
                seen.add(lbl)
                expiries.append(lbl)
        _SS[key] = expiries
        return expiries
    except Exception as e:
        st.error(f"Failed to load expiries for {index}: {e}")
        return []


def get_strikes(index, expiry_label):
    """Get sorted strike list for given index and expiry. Cached in session state."""
    code = _label_to_code(expiry_label, index)
    _SS = st.session_state
    key = f"stk_{index}_{code}"
    if key in _SS and _SS[key]:
        return _SS[key]

    try:
        resp = get_option_chain(index)
        strikes = set()
        for opt in resp.get("data", {}).get("optionsChain", []):
            exp = opt.get("expiryDate", "")
            if exp == expiry_label:
                sp = opt.get("strikePrice", 0)
                if sp:
                    strikes.add(int(float(str(sp).replace(",", ""))))
        result = sorted(strikes)
        _SS[key] = result
        return result
    except Exception:
        return []


def get_spot_price(index):
    """Get current spot price for an index."""
    try:
        sym = INDEX_SYMBOLS.get(index)
        if not sym:
            return 0.0
        q = get_quotes([sym])
        return q.get(sym, {}).get("ltp", 0.0)
    except Exception:
        return 0.0


# ── Quotes ───────────────────────────────────────────────────────────────────

def get_quotes(symbols):
    """
    Batch quotes from Fyers.
    Returns dict: symbol → {ltp, bid, ask, prev_close, open, high, low, volume, oi}
    Always falls back to prev_close_price when lp=0 (market closed).
    """
    if not symbols:
        return {}

    try:
        fyers = get_fyers_client()
        sym_str = ",".join(symbols) if isinstance(symbols, list) else symbols
        resp = fyers.quotes(data={"symbols": sym_str})

        result = {}
        for d in resp.get("d", []):
            v = d.get("v", {})
            sym = v.get("symbol", d.get("n", ""))
            ltp = v.get("lp", 0)
            prev = v.get("prev_close_price", 0)
            if ltp == 0:
                ltp = prev
            result[sym] = {
                "ltp": round(ltp, 2),
                "bid": round(v.get("bid", 0), 2),
                "ask": round(v.get("ask", 0), 2),
                "prev_close": round(prev, 2),
                "open": round(v.get("open_price", 0), 2),
                "high": round(v.get("high_price", 0), 2),
                "low": round(v.get("low_price", 0), 2),
                "volume": v.get("volume", 0),
                "oi": v.get("open_interest", v.get("oi", 0)),
                "ch": round(v.get("ch", 0), 2),
                "chp": round(v.get("chp", 0), 2),
            }
        return result
    except Exception:
        return {}


# ── Candles ──────────────────────────────────────────────────────────────────

def get_candles(symbol, resolution="1", range_from=None, range_to=None):
    """
    Fetch OHLCV candle data. Timestamps converted from UTC to IST.
    Returns DataFrame with columns: timestamp, open, high, low, close, volume
    """
    if range_from is None:
        today = get_ist_now().strftime("%Y-%m-%d")
        range_from = today
        range_to = today

    try:
        fyers = get_fyers_client()
        resp = fyers.history(
            data={
                "symbol": symbol,
                "resolution": str(resolution),
                "date_format": "1",
                "range_from": range_from,
                "range_to": range_to or range_from,
                "cont_flag": "1",
            }
        )

        candles = resp.get("candles", [])
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(
            candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = (
            pd.to_datetime(df["timestamp"], unit="s")
            .dt.tz_localize("UTC")
            .dt.tz_convert("Asia/Kolkata")
            .dt.tz_localize(None)
        )
        return df
    except Exception:
        return pd.DataFrame()


# ── Black-Scholes (Pure Python) ──────────────────────────────────────────────

def _norm_cdf(x):
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S, K, T, r, sigma, opt_type="CE"):
    """
    Black-Scholes option price.
    S=spot, K=strike, T=years to expiry, r=risk-free rate, sigma=volatility
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        intrinsic = max(0, (S - K) if opt_type == "CE" else (K - S))
        return intrinsic

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if opt_type == "CE":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_greeks(S, K, T, r, sigma, opt_type="CE"):
    """
    Calculate option Greeks: delta, gamma, vega, theta.
    Vega is per 1% move in vol. Theta is per day.
    """
    if T <= 1e-10 or sigma <= 1e-10 or S <= 0 or K <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    gamma = _norm_pdf(d1) / (S * sigma * sqrtT)
    vega = S * _norm_pdf(d1) * sqrtT / 100.0  # per 1% vol move

    if opt_type == "CE":
        delta = _norm_cdf(d1)
        theta = (
            -(S * _norm_pdf(d1) * sigma) / (2 * sqrtT)
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
        ) / 365.0
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (
            -(S * _norm_pdf(d1) * sigma) / (2 * sqrtT)
            + r * K * math.exp(-r * T) * _norm_cdf(-d2)
        ) / 365.0

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
    }


def implied_vol(price, S, K, T, r, opt_type="CE"):
    """Calculate implied volatility via bisection method."""
    if T <= 0 or price <= 0 or S <= 0 or K <= 0:
        return 0.0

    low, high = 0.001, 5.0
    mid = 0.5
    for _ in range(200):
        mid = (low + high) / 2.0
        p = bs_price(S, K, T, r, mid, opt_type)
        if abs(p - price) < 0.001:
            break
        if p > price:
            high = mid
        else:
            low = mid
    return round(mid * 100, 2)  # Return as percentage


def time_to_expiry_years(expiry_label):
    """Calculate T in years from expiry label to now."""
    try:
        m = re.match(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{2})", expiry_label.strip())
        if not m:
            return 0.0
        dd, mon, yy = m.groups()
        exp_date = datetime(
            2000 + int(yy), MONTH_NUM[mon], int(dd), 15, 30
        )
        now = get_ist_now().to_pydatetime()
        diff = (exp_date - now).total_seconds()
        if diff <= 0:
            return 0.0
        return diff / (365.25 * 24 * 3600)
    except Exception:
        return 0.0


# ── Spread Calculation Helpers ───────────────────────────────────────────────

def compute_spread_value(legs, quotes_dict):
    """
    Compute combined spread value from legs.
    Each leg: {symbol, buy_sell, ratio, lot_size}
    """
    val = 0.0
    for leg in legs:
        sym = leg["symbol"]
        q = quotes_dict.get(sym, {})
        ltp = q.get("ltp", 0)
        mult = leg.get("ratio", 1) * leg.get("lot_size", 1)
        if leg["buy_sell"] == "Buy":
            val += ltp * mult
        else:
            val -= ltp * mult
    return round(val, 2)


def get_spread_value(legs):
    """Fetch live quotes and compute spread. Returns (value, error_msg)."""
    try:
        syms = [lg["symbol"] for lg in legs if lg.get("symbol")]
        if not syms:
            return 0.0, "No symbols"
        quotes = get_quotes(syms)
        if not quotes:
            return 0.0, "No quotes returned"
        val = compute_spread_value(legs, quotes)
        return val, None
    except Exception as e:
        return 0.0, str(e)


# ── Plotly Chart Defaults ────────────────────────────────────────────────────

def dark_chart_layout(title="", height=500, yaxis_title="", xaxis_title=""):
    """Return standard Plotly layout dict in Bloomberg/TradingView dark style."""
    return dict(
        title=dict(text=title, font=dict(color="#d1d4dc", size=14)),
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        font=dict(color="#d1d4dc", family="Inter, sans-serif"),
        height=height,
        margin=dict(l=10, r=60, t=40, b=40),
        xaxis=dict(
            gridcolor="#1e222d",
            zerolinecolor="#2a2e39",
            tickfont=dict(color="#787b86"),
            title=xaxis_title,
        ),
        yaxis=dict(
            gridcolor="#1e222d",
            zerolinecolor="#2a2e39",
            tickfont=dict(color="#787b86"),
            side="right",
            title=yaxis_title,
        ),
        legend=dict(
            bgcolor="rgba(30,34,45,0.8)",
            font=dict(color="#d1d4dc", size=11),
        ),
        hovermode="x unified",
    )
