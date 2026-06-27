"""
fyers_client.py — Option Matrix v2
====================================
Fyers API v3 — Auto TOTP token generation + all data functions.

SECRETS needed in Streamlit Cloud → Settings → Secrets:
  FYERS_CLIENT_ID  = "XXXX-100"
  FYERS_SECRET_KEY = "your_secret"
  FYERS_USERNAME   = "XA12345"
  FYERS_PIN        = "1234"
  FYERS_TOTP_KEY   = "BASE32SECRETSTRING..."

How to find FYERS_TOTP_KEY:
  myapi.fyers.in → Profile → Security → TOTP → "View Secret"
  Copy the long Base32 string (NOT the 6-digit rotating code)

Redirect URL in Fyers app dashboard (myapi.fyers.in → Apps → Edit):
  Must be exactly: http://127.0.0.1:8080/
"""

import os, re, math, json, base64, hashlib, time
import streamlit as st
import requests
import pyotp
import pandas as pd
from datetime import datetime, date
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from fyers_apiv3 import fyersModel

# ── Constants ─────────────────────────────────────────────────────────────────
TOKEN_FILE     = "fyers_token.json"
REDIRECT_URI   = "http://127.0.0.1:8080/"
RISK_FREE_RATE = 0.07

LOT_SIZES = {"NIFTY": 75, "SENSEX": 20, "BANKNIFTY": 35, "FINNIFTY": 40}

INDEX_SYMBOLS = {
    "NIFTY":     "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "SENSEX":    "BSE:SENSEX-INDEX",
    "FINNIFTY":  "NSE:FINNIFTY-INDEX",
}

LEG_COLORS = {
    1: "#2962ff", 2: "#26a69a", 3: "#ff9800",
    4: "#ef5350", 5: "#9c27b0", 6: "#00bcd4",
}

_MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
_MNUM   = {m: i+1 for i, m in enumerate(_MONTHS)}

# ── Time helpers ──────────────────────────────────────────────────────────────
def ist_now():
    """Current IST time as tz-naive Timestamp. Streamlit Cloud runs UTC."""
    return pd.Timestamp.now(tz="Asia/Kolkata").replace(tzinfo=None)

def is_market_open():
    now = ist_now()
    if now.weekday() >= 5: return False
    from datetime import time as _t
    return _t(9, 15) <= now.time() <= _t(15, 30)

def market_badge_html():
    now = ist_now()
    ts  = now.strftime("%H:%M:%S")
    if is_market_open():
        return (f'<span style="color:#26a69a;font-weight:600;">🟢 OPEN</span> '
                f'<span style="color:#787b86;font-size:11px;">{ts} IST</span>')
    return (f'<span style="color:#ef5350;font-weight:600;">🔴 CLOSED</span> '
            f'<span style="color:#787b86;font-size:11px;">{ts} IST</span>')

# ── Secrets helper ────────────────────────────────────────────────────────────
def _sec(k):
    try:
        if k in st.secrets: return str(st.secrets[k]).strip()
    except Exception: pass
    return os.environ.get(k, "").strip()

def _b64(v): return base64.b64encode(str(v).encode()).decode()

# ── Token file ────────────────────────────────────────────────────────────────
def _save_token(token):
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token, "date": date.today().isoformat()}, f)
    except Exception: pass

def _load_token():
    try:
        d = json.load(open(TOKEN_FILE))
        if d.get("date") == date.today().isoformat() and len(d.get("token","")) > 20:
            return d["token"]
    except Exception: pass
    return None

# ── TOTP 5-step login ─────────────────────────────────────────────────────────
def _totp_login():
    """
    Generate Fyers access token via TOTP.
    Step 4 extracts auth_code from the "Url" field in POST /api/v3/token response.
    This is the ONLY reliable method on Streamlit Cloud — the GET generate-authcode
    approach fails because it redirects to localhost which is blocked on cloud servers.
    """
    cid    = _sec("FYERS_CLIENT_ID")
    sec    = _sec("FYERS_SECRET_KEY")
    user   = _sec("FYERS_USERNAME")
    pin    = _sec("FYERS_PIN")
    totp_k = _sec("FYERS_TOTP_KEY")
    app_id = cid.split("-")[0]

    sess = requests.Session()

    # ── Step 1: Send OTP ──────────────────────────────────────────────────────
    r1 = sess.post(
        "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
        json={"fy_id": _b64(user), "app_id": "2"},
        timeout=15)
    if r1.status_code == 429:
        raise RuntimeError(
            "Fyers rate limited (429). Wait 60 seconds then click Refresh Token.")
    d1 = r1.json()
    if d1.get("s") != "ok":
        raise RuntimeError(f"Step 1 (send OTP) failed: {d1}")

    # ── Step 2: Verify TOTP ───────────────────────────────────────────────────
    r2 = sess.post(
        "https://api-t2.fyers.in/vagator/v2/verify_otp",
        json={"request_key": d1["request_key"],
              "otp": pyotp.TOTP(totp_k).now()},
        timeout=15)
    d2 = r2.json()
    if d2.get("s") != "ok":
        raise RuntimeError(
            f"Step 2 (TOTP verify) failed: {d2}\n"
            "→ FYERS_TOTP_KEY must be the Base32 secret from TOTP setup "
            "(myapi.fyers.in → Profile → Security → TOTP → View Secret)\n"
            "→ It looks like: MM3N4EAJDKRHPNEP... NOT the 6-digit code")

    # ── Step 3: Verify PIN ────────────────────────────────────────────────────
    r3 = sess.post(
        "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
        json={"request_key": d2["request_key"],
              "identity_type": "pin",
              "identifier": _b64(pin)},
        timeout=15)
    d3 = r3.json()
    if d3.get("s") != "ok" or "access_token" not in d3.get("data", {}):
        raise RuntimeError(
            f"Step 3 (PIN verify) failed: {d3}\n"
            "→ Check FYERS_PIN — it is your 4-digit Fyers login PIN")
    bearer = d3["data"]["access_token"]

    # ── Step 4: Get auth_code ─────────────────────────────────────────────────
    # POST to /api/v3/token with bearer token as Authorization header.
    # Response contains "Url" field like:
    #   "http://127.0.0.1:8080/?auth_code=eyJhbGci...&state=sample"
    # Parse auth_code directly from this URL — NO redirect/GET needed.
    r4 = sess.post(
        "https://api-t1.fyers.in/api/v3/token",
        json={
            "fyers_id":       user,
            "app_id":         app_id,
            "redirect_uri":   REDIRECT_URI,
            "appType":        "100",
            "code_challenge": "",
            "state":          "sample",
            "scope":          "",
            "nonce":          "",
            "response_type":  "code",
            "create_cookie":  True,
        },
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=15)
    d4 = r4.json()
    if d4.get("s") != "ok":
        raise RuntimeError(
            f"Step 4 (get auth_code) failed: {d4}\n"
            f"→ 'redirectUrl mismatch': Go to myapi.fyers.in → Apps → your app → Edit\n"
            f"  Set Redirect URL to exactly: {REDIRECT_URI}\n"
            f"→ 'apptype mismatch': FYERS_CLIENT_ID must end with -100 (e.g. ABC123-100)")

    # Extract auth_code — it is inside the "Url" field in the response
    auth_code = None
    data_field = d4.get("data", {})

    # Primary: parse from "Url" field in response body
    for url_key in ("Url", "url", "URL"):
        url_val = d4.get(url_key) or data_field.get(url_key, "")
        if url_val and "auth_code=" in url_val:
            auth_code = parse_qs(urlparse(url_val).query).get("auth_code", [None])[0]
            if auth_code:
                break

    # Fallback: "auth" or "auth_code" directly in data
    if not auth_code:
        auth_code = data_field.get("auth_code") or data_field.get("auth")

    # Fallback: check Location header if any redirect happened
    if not auth_code:
        loc = r4.headers.get("Location", "")
        if "auth_code=" in loc:
            auth_code = parse_qs(urlparse(loc).query).get("auth_code", [None])[0]

    if not auth_code:
        raise RuntimeError(
            f"Step 4: Could not extract auth_code from response.\n"
            f"Full response: {d4}\n"
            f"Headers: {dict(r4.headers)}")

    # ── Step 5: Exchange auth_code for access_token ───────────────────────────
    app_hash = hashlib.sha256(f"{app_id}:{sec}".encode()).hexdigest()
    r5 = sess.post(
        "https://api-t1.fyers.in/api/v3/validate-authcode",
        json={"grant_type":  "authorization_code",
              "appIdHash":   app_hash,
              "code":        auth_code},
        timeout=15)
    d5    = r5.json()
    token = d5.get("access_token")

    if not token:
        # SDK fallback
        try:
            sm = fyersModel.SessionModel(
                client_id=cid, secret_key=sec, redirect_uri=REDIRECT_URI,
                response_type="code", grant_type="authorization_code")
            sm.set_token(auth_code)
            d5b   = sm.generate_token()
            token = d5b.get("access_token")
        except Exception as sdk_err:
            raise RuntimeError(
                f"Step 5 (validate authcode) failed.\n"
                f"Primary: {d5}\nSDK fallback: {sdk_err}")

    if not token:
        raise RuntimeError(f"Step 5: No access_token in response: {d5}")

    return token

# ── Public auth API ───────────────────────────────────────────────────────────
def get_token():
    """
    Returns a valid Fyers access token.
    1. Check st.session_state (per session, fastest)
    2. Check fyers_token.json (survives hot-reloads, one token per day)
    3. Generate fresh via TOTP (once per day, auto)
    """
    t = st.session_state.get("_fyers_tok")
    if t and len(t) > 20: return t

    t = _load_token()
    if t:
        st.session_state["_fyers_tok"] = t
        return t

    miss = [k for k in ["FYERS_CLIENT_ID","FYERS_SECRET_KEY",
                         "FYERS_USERNAME","FYERS_PIN","FYERS_TOTP_KEY"]
            if not _sec(k)]
    if miss:
        raise RuntimeError(
            f"Missing Fyers secrets: {', '.join(miss)}\n\n"
            "Add them in Streamlit Cloud → your app → ⋮ → Settings → Secrets:\n"
            '  FYERS_CLIENT_ID  = "XXXX-100"\n'
            '  FYERS_SECRET_KEY = "your_secret"\n'
            '  FYERS_USERNAME   = "XA12345"\n'
            '  FYERS_PIN        = "1234"\n'
            '  FYERS_TOTP_KEY   = "MM3N4EAJDKRHPNEP..."')

    token = _totp_login()
    _save_token(token)
    st.session_state["_fyers_tok"] = token
    return token

def get_fyers():
    """Returns authenticated FyersModel. Cached in session state."""
    if st.session_state.get("_fc"): return st.session_state["_fc"]
    fc = fyersModel.FyersModel(
        client_id=_sec("FYERS_CLIENT_ID"),
        token=get_token(), is_async=False, log_path="")
    st.session_state["_fc"] = fc
    return fc

def refresh_token():
    """Force fresh token on next call. Call when data stops updating."""
    st.session_state.pop("_fc", None)
    st.session_state.pop("_fyers_tok", None)
    try: os.remove(TOKEN_FILE)
    except FileNotFoundError: pass
    for k in list(st.session_state.keys()):
        if k.startswith("exp_") or k.startswith("stk_"): del st.session_state[k]

# ── Expiries ──────────────────────────────────────────────────────────────────
def get_expiries(index):
    """Load expiry labels from Fyers optionchain. Cached in session state."""
    ck = f"exp_{index}"
    if st.session_state.get(ck): return list(st.session_state[ck].keys())

    fc  = get_fyers()
    sym = INDEX_SYMBOLS.get(index, f"NSE:{index}-INDEX")
    r   = fc.optionchain(data={"symbol": sym, "strikecount": 1, "timestamp": ""})
    if not (r and r.get("s") == "ok"):
        raise ValueError(f"Cannot load expiries for {index}: {r}")

    raw    = r.get("data", {}).get("expiryData", [])
    parsed = []
    for e in raw:
        if not isinstance(e, dict): continue
        try:
            dd, mm, yy4 = e["date"].split("-")
            dd, mm, yy4 = int(dd), int(mm), int(yy4)
            parsed.append((yy4%100, mm, dd, _MONTHS[mm-1]))
        except Exception: continue
    if not parsed: raise ValueError(f"No expiry dates for {index}")

    by_month = defaultdict(list)
    for yy,mm,dd,mon in parsed: by_month[(yy,mm)].append(dd)
    last = {k: max(v) for k,v in by_month.items()}

    result = {}
    for yy,mm,dd,mon in parsed:
        is_m  = (dd == last[(yy,mm)])
        code  = f"{yy:02d}{mon}" if is_m else f"{yy:02d}{mm:02d}{dd:02d}"
        label = f"{dd:02d} {mon} {yy:02d} ({'M' if is_m else 'W'})"
        result[label] = code

    st.session_state[ck] = result
    return list(result.keys())

def _label_to_code(label, index="NIFTY"):
    """
    Convert expiry label → Fyers code. Works WITHOUT session state.
    "19 MAY 26 (W)" → "260519"
    "29 MAY 26 (M)" → "26MAY"
    """
    # 1. Session state cache
    cached = st.session_state.get(f"exp_{index}", {}).get(label)
    if cached: return cached

    # 2. Direct parse (works even on cold start)
    try:
        clean  = re.sub(r'\s*\([WM]\)\s*$', '', label.strip(), flags=re.IGNORECASE).strip()
        parts  = clean.split()
        dd, mon, yy = int(parts[0]), parts[1][:3].upper(), int(parts[2])
        mm = _MNUM.get(mon, 0)
        if mm > 0:
            is_m = bool(re.search(r'\(M\)', label, re.IGNORECASE))
            return f"{yy:02d}{mon}" if is_m else f"{yy:02d}{mm:02d}{dd:02d}"
    except Exception: pass
    return label.strip()

def _expiry_date(label, index="NIFTY"):
    """Get expiry as date object from label."""
    import calendar
    code = _label_to_code(label, index).upper()
    if any(c.isalpha() for c in code):
        yy=int(code[:2]); mon=code[2:5]; mm=_MNUM[mon]
        return date(2000+yy, mm, calendar.monthrange(2000+yy,mm)[1])
    return date(2000+int(code[:2]), int(code[2:4]), int(code[4:6]))

def _dte(label, index="NIFTY"):
    """Days to expiry as fraction of year."""
    try: return max((_expiry_date(label,index)-date.today()).days, 1)/365.
    except Exception: return 30/365.

# ── Strikes ───────────────────────────────────────────────────────────────────
def get_strikes(index, expiry_label):
    """All strikes for index+expiry. strikecount=0 → full chain."""
    code = _label_to_code(expiry_label, index)
    ck   = f"stk_{index}_{code}"
    if st.session_state.get(ck): return st.session_state[ck]

    fc  = get_fyers()
    sym = INDEX_SYMBOLS.get(index, f"NSE:{index}-INDEX")
    r   = fc.optionchain(data={"symbol": sym, "strikecount": 0, "timestamp": ""})
    if r and r.get("s") == "ok":
        chain   = r.get("data", {}).get("optionsChain", [])
        strikes = sorted({int(float(o["strikePrice"]))
                          for o in chain if isinstance(o,dict) and o.get("strikePrice")})
        if strikes:
            st.session_state[ck] = strikes
            return strikes

    atm  = {"NIFTY":22800,"SENSEX":82500,"BANKNIFTY":48000}.get(index, 22800)
    step = 50 if index=="NIFTY" else (100 if index=="BANKNIFTY" else 500)
    return list(range(atm-40*step, atm+41*step, step))

# ── Symbol builder ────────────────────────────────────────────────────────────
def build_symbol(index, expiry_label, opt_type, strike):
    """
    Build valid Fyers option symbol.
    Weekly:  NSE:NIFTY26519CE23750   (code 260519 → 26+5+19, no leading zero on month)
    Monthly: NSE:NIFTY26MAYCE23000   (code 26MAY)
    SENSEX:  BSE:SENSEX26MAYCE82000
    """
    exch = "BSE" if index in ("SENSEX","BANKEX") else "NSE"
    code = _label_to_code(expiry_label, index).strip().upper()
    ot   = "CE" if opt_type.upper() in ("CE","C","CALL") else "PE"
    stk  = str(int(float(str(strike).replace(",",""))))

    if any(c.isalpha() for c in code):           # Monthly: 26MAY
        return f"{exch}:{index}{code}{ot}{stk}"
    if len(code) == 6 and code.isdigit():         # Weekly: 260519
        yy = code[:2]
        mm = str(int(code[2:4]))                  # "05" → "5"
        dd = code[4:6]
        return f"{exch}:{index}{yy}{mm}{dd}{ot}{stk}"
    return f"{exch}:{index}{code}{ot}{stk}"

# ── Live quotes ───────────────────────────────────────────────────────────────
def get_quotes(symbols):
    """
    Batch quotes in ONE API call.
    Returns dict: symbol → {ltp, bid, ask, prev_close, high, low, oi, volume}
    Uses prev_close when lp=0 (market closed).
    """
    if not symbols: return {}
    try:
        fc   = get_fyers()
        syms = ",".join(symbols) if isinstance(symbols, list) else symbols
        r    = fc.quotes(data={"symbols": syms})
        if r.get("s") != "ok": return {}
        out = {}
        for d in r.get("d", []):
            v   = d.get("v", {})
            sym = v.get("symbol") or d.get("n","")
            ltp = float(v.get("lp", 0))
            pre = float(v.get("prev_close_price", 0))
            eff = ltp if ltp > 0 else pre
            out[sym] = {
                "ltp":        eff,
                "ltp_live":   ltp,
                "prev_close": pre,
                "bid":        float(v.get("bid", eff*.998)),
                "ask":        float(v.get("ask", eff*1.002)),
                "high":       float(v.get("high_price", eff)),
                "low":        float(v.get("low_price",  eff)),
                "oi":         int(v.get("open_interest", v.get("oi", 0))),
                "volume":     int(v.get("volume", 0)),
                "ch":         float(v.get("ch", 0)),
                "chp":        float(v.get("chp", 0)),
                "market_open": ltp > 0,
            }
        return out
    except Exception: return {}

def get_ltp(index, strike, expiry, cp):
    """Single option LTP."""
    sym = build_symbol(index, expiry, cp, strike)
    return get_quotes([sym]).get(sym, {}).get("ltp", 0.0)

def get_spot(index):
    """Underlying spot price."""
    try: return get_quotes([INDEX_SYMBOLS[index]]).get(INDEX_SYMBOLS[index], {}).get("ltp", 0.0)
    except: return {"NIFTY":22800,"SENSEX":82500,"BANKNIFTY":48000}.get(index,22800)

def get_spread_value(legs):
    """
    Compute live spread value for all legs in ONE batch quote call.
    Returns (value, error_or_None).
    """
    syms    = []
    sym_map = {}
    for leg in legs:
        try:
            sym = build_symbol(leg["index"], leg["expiry"], leg["cp"], leg["strike"])
            syms.append(sym)
            sym_map[sym] = leg
        except Exception: pass
    if not syms: return 0.0, "No valid symbols"

    quotes = get_quotes(syms)
    if not quotes: return 0.0, "No quotes returned — check token"

    total = 0.0; missing = []
    for sym, leg in sym_map.items():
        ltp = quotes.get(sym, {}).get("ltp", 0.0)
        if ltp:
            sign   = 1 if leg["bs"] == "Buy" else -1
            total += sign * ltp * leg.get("ratio", 1)
        else:
            missing.append(f"{leg['index']} {leg['strike']}{leg['cp']}")

    err = f"No price: {', '.join(missing)}" if missing else None
    return round(total, 2), err

# ── Candles ───────────────────────────────────────────────────────────────────
def get_candles(symbol, resolution="1", from_date=None, to_date=None):
    """
    OHLCV candles. Timestamps converted UTC→IST.
    Returns DataFrame: timestamp, open, high, low, close, volume.
    """
    today = ist_now().strftime("%Y-%m-%d")
    if from_date is None: from_date = today
    if to_date   is None: to_date   = today
    try:
        fc = get_fyers()
        r  = fc.history(data={"symbol": symbol, "resolution": str(resolution),
                               "date_format": "1", "range_from": from_date,
                               "range_to": to_date, "cont_flag": "1"})
        if not (r.get("s") == "ok" and r.get("candles")):
            return pd.DataFrame()
        df = pd.DataFrame(r["candles"], columns=["timestamp","open","high","low","close","volume"])
        df["timestamp"] = (pd.to_datetime(df["timestamp"], unit="s")
                           .dt.tz_localize("UTC")
                           .dt.tz_convert("Asia/Kolkata")
                           .dt.tz_localize(None))
        return df
    except Exception: return pd.DataFrame()

def get_spread_candles(legs, resolution="1", from_date=None, to_date=None):
    """Combine per-leg candles into spread OHLCV."""
    spread = base_ts = None
    for leg in legs:
        sym = build_symbol(leg["index"], leg["expiry"], leg["cp"], leg["strike"])
        df  = get_candles(sym, resolution, from_date, to_date)
        if df.empty: continue
        s = df.set_index("timestamp")["close"] * leg.get("ratio", 1)
        s = s if leg["bs"] == "Buy" else -s
        if spread is None: spread, base_ts = s, df["timestamp"].values
        else: spread = spread.add(s, fill_value=0)
    if spread is None: return pd.DataFrame()
    out = pd.DataFrame({"timestamp": base_ts, "close": spread.values})
    out["open"]  = out["close"].shift(1).fillna(out["close"])
    out["high"]  = out[["open","close"]].max(axis=1)
    out["low"]   = out[["open","close"]].min(axis=1)
    return out.reset_index(drop=True)

# ── Black-Scholes ─────────────────────────────────────────────────────────────
def _N(x): return (1+math.erf(x/math.sqrt(2)))/2
def _n(x): return math.exp(-.5*x*x)/math.sqrt(2*math.pi)

def bs_price(S,K,T,r,sig,cp):
    if T<=0 or sig<=0: return max(0.,(S-K) if cp=="CE" else(K-S))
    d1=(math.log(S/K)+(r+.5*sig**2)*T)/(sig*math.sqrt(T)); d2=d1-sig*math.sqrt(T)
    return S*_N(d1)-K*math.exp(-r*T)*_N(d2) if cp=="CE" else K*math.exp(-r*T)*_N(-d2)-S*_N(-d1)

def implied_vol(mp,S,K,T,r,cp):
    if any(x<=0 for x in [mp,S,K,T]): return 0.
    lo,hi=.001,5.
    for _ in range(200):
        mid=(lo+hi)/2; p=bs_price(S,K,T,r,mid,cp)
        if abs(p-mp)<1e-4: return round(mid*100,2)
        lo,hi=(mid,hi) if p<mp else(lo,mid)
    return round(mid*100,2)

def bs_greeks(S,K,T,r,sig,cp):
    if T<=0 or sig<=0: return{"delta":0,"gamma":0,"vega":0,"theta":0}
    d1=(math.log(S/K)+(r+.5*sig**2)*T)/(sig*math.sqrt(T)); d2=d1-sig*math.sqrt(T)
    pdf=_n(d1); g=pdf/(S*sig*math.sqrt(T)); v=S*pdf*math.sqrt(T)/100
    d=_N(d1) if cp=="CE" else _N(d1)-1
    t=(-(S*pdf*sig)/(2*math.sqrt(T))+(-r*K*math.exp(-r*T)*_N(d2) if cp=="CE"
       else r*K*math.exp(-r*T)*_N(-d2)))/365
    return{"delta":round(d,4),"gamma":round(g,6),"vega":round(v,4),"theta":round(t,4)}

def get_net_greeks(legs):
    """Net Greeks across all legs using live LTPs."""
    net={"delta":0.,"gamma":0.,"vega":0.,"theta":0.,"ivs":[]}
    for leg in legs:
        try:
            S=get_spot(leg["index"]); K=float(leg["strike"])
            T=_dte(leg["expiry"],leg["index"])
            ltp=get_ltp(leg["index"],leg["strike"],leg["expiry"],leg["cp"])
            iv=implied_vol(ltp,S,K,T,RISK_FREE_RATE,leg["cp"])
            g=bs_greeks(S,K,T,RISK_FREE_RATE,iv/100,leg["cp"])
            sgn=1 if leg["bs"]=="Buy" else -1; r=leg.get("ratio",1)
            for k in("delta","gamma","vega","theta"): net[k]+=sgn*r*g[k]
            net["ivs"].append(iv)
        except Exception: pass
    return{"delta":round(net["delta"],4),"gamma":round(net["gamma"],6),
           "vega":round(net["vega"],4),"theta":round(net["theta"],4),
           "net_iv":round(sum(net["ivs"])/len(net["ivs"]),2) if net["ivs"] else 0.}

# ── Chart layout ──────────────────────────────────────────────────────────────
def dark_layout(title="", height=480):
    return dict(
        title=dict(text=title, font=dict(color="#d1d4dc",size=13)),
        paper_bgcolor="#131722", plot_bgcolor="#131722",
        font=dict(color="#d1d4dc", family="Inter,sans-serif"),
        height=height, margin=dict(l=10,r=60,t=40,b=40),
        xaxis=dict(gridcolor="#1e222d", zerolinecolor="#2a2e39",
                   tickfont=dict(color="#787b86"), rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#1e222d", zerolinecolor="#2a2e39",
                   tickfont=dict(color="#787b86"), side="right"),
        legend=dict(bgcolor="rgba(30,34,45,0.8)", font=dict(color="#d1d4dc",size=11)),
        hovermode="x unified")

# ── Sidebar widget ────────────────────────────────────────────────────────────
def render_token_status():
    """Sidebar: market status badge + Refresh Token button."""
    st.markdown(market_badge_html(), unsafe_allow_html=True)
    col1, col2 = st.columns([3,1])
    with col1:
        tok = st.session_state.get("_fyers_tok") or _load_token()
        if tok:
            st.markdown('<span style="font-size:11px;color:#26a69a;">🔑 Token active</span>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<span style="font-size:11px;color:#ff9800;">⏳ Token loading...</span>',
                        unsafe_allow_html=True)
    with col2:
        if st.button("🔄", key="_refresh_tok", help="Refresh Fyers token"):
            refresh_token(); st.rerun()
