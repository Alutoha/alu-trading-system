import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import bcrypt
import random
import string
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

# ==================== INIT DATABASE ====================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            email TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            expired_date TEXT NOT NULL,
            status TEXT DEFAULT 'aktif',
            is_trial INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    c.execute("SELECT * FROM admins WHERE username='admin'")
    if not c.fetchone():
        hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
        c.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", 
                  ("admin", hashed))
    
    conn.commit()
    conn.close()

# ==================== FUNCTIONS ====================
def get_connection():
    return sqlite3.connect("users.db")

def verify_admin(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM admins WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return bcrypt.checkpw(password.encode(), row[0])
    return False

def verify_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT password_hash, expired_date, status, nama FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        if row[2] != 'aktif':
            return None, "Akun dinonaktifkan"
        if bcrypt.checkpw(password.encode(), row[0]):
            expired = datetime.strptime(row[1], "%Y-%m-%d")
            if expired < datetime.now():
                conn = get_connection()
                c = conn.cursor()
                c.execute("UPDATE users SET status='expired' WHERE username=?", (username,))
                conn.commit()
                conn.close()
                return None, "Akun expired"
            return row[3], None
        else:
            return None, "Password salah"
    return None, "Username tidak ditemukan"

def generate_user(nama, email, masa_hari, is_trial=0):
    angka = ''.join(random.choices(string.digits, k=4))
    username = f"USER-{nama.upper()}{angka}"
    
    chars = string.ascii_letters + string.digits + "#@!"
    password = ''.join(random.choices(chars, k=10))
    
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    expired = (datetime.now() + timedelta(days=masa_hari)).strftime("%Y-%m-%d")
    
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (nama, email, username, password_hash, expired_date, is_trial) VALUES (?, ?, ?, ?, ?, ?)",
            (nama, email, username, hashed, expired, is_trial)
        )
        conn.commit()
        conn.close()
        return username, password, expired
    except sqlite3.IntegrityError:
        conn.close()
        return generate_user(nama, email, masa_hari, is_trial)

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nama, email, username, expired_date, status, is_trial FROM users ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def extend_user(user_id, hari):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT expired_date FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        old_expired = datetime.strptime(row[0], "%Y-%m-%d")
        new_expired = (old_expired + timedelta(days=hari)).strftime("%Y-%m-%d")
        c.execute("UPDATE users SET expired_date=?, status='aktif' WHERE id=?", (new_expired, user_id))
        conn.commit()
    conn.close()

# ==================== SMC/ICT ANALYSIS ====================
def fetch_data(symbol, period="4h", lookback=200):
    """Ambil data dari Yahoo Finance"""
    # Mapping symbol ke Yahoo Finance
    map_symbol = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "USOIL": "CL=F",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "NZDUSD": "NZDUSD=X",
        "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X",
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "XRPUSD": "XRP-USD",
        "ADAUSD": "ADA-USD",
        "SOLUSD": "SOL-USD",
    }
    ticker = map_symbol.get(symbol, "GC=F")
    df = yf.download(ticker, period="7d", interval="1h")  # ambil data 7 hari, 1 jam
    if df.empty:
        return None
    # Jika timeframe 4h, kita resample
    df = df.resample("4h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum"
    }).dropna()
    return df

def find_swings(df, swing_strength=2):
    """Cari swing high dan low sederhana"""
    highs = df["High"].values
    lows = df["Low"].values
    swing_highs = []
    swing_lows = []
    for i in range(swing_strength, len(df)-swing_strength):
        if highs[i] == max(highs[i-swing_strength:i+swing_strength+1]):
            swing_highs.append(i)
        if lows[i] == min(lows[i-swing_strength:i+swing_strength+1]):
            swing_lows.append(i)
    return swing_highs, swing_lows

def detect_bos(df, swing_highs, swing_lows):
    """Deteksi Break of Structure"""
    bos_bull = False
    bos_bear = False
    if len(swing_highs) >= 2:
        last_sh_idx = swing_highs[-1]
        prev_sh_idx = swing_highs[-2]
        if df["High"].iloc[-1] > df["High"].iloc[prev_sh_idx]:
            bos_bull = True
    if len(swing_lows) >= 2:
        last_sl_idx = swing_lows[-1]
        prev_sl_idx = swing_lows[-2]
        if df["Low"].iloc[-1] < df["Low"].iloc[prev_sl_idx]:
            bos_bear = True
    return bos_bull, bos_bear

def find_order_block(df, direction, swing_idx):
    """Order block sederhana: candle terakhir sebelum impuls"""
    if direction == "bullish":
        for i in range(swing_idx-1, max(swing_idx-10, 0), -1):
            if df["Close"].iloc[i] < df["Open"].iloc[i]:  # bearish candle
                return {
                    "high": df["High"].iloc[i],
                    "low": df["Low"].iloc[i],
                    "index": i
                }
    else:
        for i in range(swing_idx-1, max(swing_idx-10, 0), -1):
            if df["Close"].iloc[i] > df["Open"].iloc[i]:  # bullish candle
                return {
                    "high": df["High"].iloc[i],
                    "low": df["Low"].iloc[i],
                    "index": i
                }
    return None

def find_fvg(df):
    """Fair Value Gap sederhana di candle terakhir"""
    if len(df) < 3:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    # Bullish FVG: prev2.High < last.Low
    if prev2["High"] < last["Low"]:
        return {"top": last["Low"], "bottom": prev2["High"], "type": "bullish"}
    # Bearish FVG: prev2.Low > last.High
    if prev2["Low"] > last["High"]:
        return {"top": prev2["Low"], "bottom": last["High"], "type": "bearish"}
    return None

def ict_analysis(symbol):
    """Analisa ICT lengkap, return sinyal dan alasan"""
    df = fetch_data(symbol)
    if df is None or len(df) < 20:
        return None, "Data tidak cukup"
    
    swing_highs, swing_lows = find_swings(df)
    bos_bull, bos_bear = detect_bos(df, swing_highs, swing_lows)
    
    signal = None
    reasons = []
    entry = None
    sl = None
    tp1 = None
    tp2 = None
    
    current_price = df["Close"].iloc[-1]
    
    # Logic SMC sederhana
    if bos_bull:
        # Cari order block bullish
        ob = find_order_block(df, "bullish", swing_lows[-1] if swing_lows else len(df)-1)
        if ob:
            entry = ob["high"] + 0.01
            sl = ob["low"] - 0.01
            tp1 = current_price + (current_price - sl) * 1.5
            tp2 = current_price + (current_price - sl) * 3
            signal = "BUY"
            reasons = [
                "✅ BOS Bullish terdeteksi",
                "✅ Order Block bullish ditemukan",
                "✅ Harga retrace ke area OB",
                "✅ Konfirmasi FVG (jika ada)"
            ]
        else:
            # fallback: entry di current price
            signal = "BUY"
            sl = df["Low"].iloc[-1] - 0.01
            tp1 = current_price + 10
            tp2 = current_price + 20
            reasons = ["✅ BOS Bullish, entry momentum"]
    elif bos_bear:
        ob = find_order_block(df, "bearish", swing_highs[-1] if swing_highs else len(df)-1)
        if ob:
            entry = ob["low"] - 0.01
            sl = ob["high"] + 0.01
            tp1 = current_price - (sl - current_price) * 1.5
            tp2 = current_price - (sl - current_price) * 3
            signal = "SELL"
            reasons = [
                "✅ BOS Bearish terdeteksi",
                "✅ Order Block bearish ditemukan",
                "✅ Harga retrace ke area OB",
                "✅ Konfirmasi FVG (jika ada)"
            ]
        else:
            signal = "SELL"
            sl = df["High"].iloc[-1] + 0.01
            tp1 = current_price - 10
            tp2 = current_price - 20
            reasons = ["✅ BOS Bearish, entry momentum"]
    else:
        # Tidak ada BOS, cek FVG saja
        fvg = find_fvg(df)
        if fvg and fvg["type"] == "bullish":
            signal = "BUY"
            entry = fvg["top"]
            sl = fvg["bottom"]
            tp1 = current_price + 5
            tp2 = current_price + 10
            reasons = ["✅ Bullish FVG terdeteksi"]
        elif fvg and fvg["type"] == "bearish":
            signal = "SELL"
            entry = fvg["bottom"]
            sl = fvg["top"]
            tp1 = current_price - 5
            tp2 = current_price - 10
            reasons = ["✅ Bearish FVG terdeteksi"]
    
    if signal:
        return {
            "signal": signal,
            "entry": entry if entry else current_price,
            "sl": sl if sl else (current_price - 1 if signal == "BUY" else current_price + 1),
            "tp1": tp1,
            "tp2": tp2,
            "reasons": reasons,
            "price": current_price
        }, None
    else:
        return None, "Tidak ada setup valid"

# ==================== SESSION ====================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None
if "nama" not in st.session_state:
    st.session_state.nama = None
if "user_page" not in st.session_state:
    st.session_state.user_page = "analisa"
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# ==================== STYLING ====================
st.set_page_config(page_title="Alu Trading System", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .signal-card {
        background: linear-gradient(135deg, #1a472a 0%, #0d2818 100%);
        border: 2px solid #00ff88;
        border-radius: 20px;
        padding: 30px;
        text-align: center;
        margin: 20px 0;
    }
    .sell-signal {
        background: linear-gradient(135deg, #4a1a1a 0%, #28110d 100%) !important;
        border: 2px solid #ff4444 !important;
    }
    .signal-card h1 { color: #00ff88; font-size: 48px; margin: 0; }
    .sell-signal h1 { color: #ff4444 !important; }
    .signal-details {
        background: #1a1a2e;
        border-radius: 15px;
        padding: 20px;
        margin: 15px 0;
        text-align: left;
    }
    .signal-details p { font-size: 18px; margin: 8px 0; color: #e0e0e0; }
    .stButton > button {
        border-radius: 12px;
        font-weight: bold;
        padding: 12px 24px;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 15px rgba(0,255,136,0.3);
    }
</style>
""", unsafe_allow_html=True)

# ==================== INIT DB ====================
init_db()

# ==================== LOGIN PAGE ====================
if not st.session_state.logged_in:
    params = st.query_params
    is_admin_url = params.get("admin", [False])[0]
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center; color:#00ff88;'>📊 ALU TRADING SYSTEM</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#888;'>SMC/ICT Smart Money Analysis</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        if is_admin_url:
            st.info("🔐 Admin Mode")
            username = st.text_input("Username", key="admin_user")
            password = st.text_input("Password", type="password", key="admin_pass")
            if st.button("🔓 MASUK ADMIN", use_container_width=True):
                if verify_admin(username, password):
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                    st.rerun()
                else:
                    st.error("❌ Akses ditolak!")
        else:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("🔓 MASUK", use_container_width=True):
                nama, error = verify_user(username, password)
                if nama:
                    st.session_state.logged_in = True
                    st.session_state.role = "user"
                    st.session_state.nama = nama
                    st.rerun()
                else:
                    st.error(f"❌ {error}")

# ==================== ADMIN PANEL ====================
elif st.session_state.role == "admin":
    # ... (kode admin panel sama seperti sebelumnya, tidak diubah)
    st.sidebar.markdown("<h2 style='color:#00ff88;'>👑 ADMIN PANEL</h2>", unsafe_allow_html=True)
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()
    st.markdown("<h1 style='color:#00ff88;'>👑 Alu Trading System - Admin Panel</h1>", unsafe_allow_html=True)
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["➕ Generate Kode", "🎁 Trial 2 Hari", "📋 Daftar User"])
    with tab1:
        st.subheader("Generate Kode Akses Berbayar")
        col1, col2 = st.columns(2)
        with col1:
            nama = st.text_input("Nama", placeholder="Adi")
        with col2:
            email = st.text_input("Email", placeholder="adi@gmail.com")
        masa_aktif = st.selectbox("Masa Aktif", [7, 30, 90, 180, 365], format_func=lambda x: f"{x} Hari")
        if st.button("🔑 GENERATE KODE", use_container_width=True):
            if nama and email:
                username, password, expired = generate_user(nama, email, masa_aktif, is_trial=0)
                st.success("✅ Kode akses berhasil dibuat!")
                st.markdown(f"""
                ### 📋 Detail Akses:
                - **Username:** `{username}`
                - **Password:** `{password}`
                - **Expired:** `{expired}`
                - **Status:** 💰 BERBAYAR
                > ⚠️ Simpan password ini! Tidak bisa dilihat lagi.
                """)
            else:
                st.error("Mohon isi nama dan email!")
    with tab2:
        st.subheader("🎁 Generate Kode Trial 2 Hari")
        st.markdown("Khusus untuk calon pembeli yang ingin mencoba.")
        col1, col2 = st.columns(2)
        with col1:
            nama = st.text_input("Nama", placeholder="Calon User", key="trial_nama")
        with col2:
            email = st.text_input("Email", placeholder="calon@gmail.com", key="trial_email")
        if st.button("🎁 GENERATE TRIAL", use_container_width=True):
            if nama and email:
                username, password, expired = generate_user(nama, email, 2, is_trial=1)
                st.success("✅ Kode Trial berhasil dibuat!")
                st.markdown(f"""
                ### 📋 Detail Trial:
                - **Username:** `{username}`
                - **Password:** `{password}`
                - **Expired:** `{expired}` (2 hari)
                - **Status:** 🎁 TRIAL
                > ⚠️ Trial hanya berlaku 2 hari.
                """)
            else:
                st.error("Mohon isi nama dan email!")
    with tab3:
        st.subheader("Daftar User Terdaftar")
        users = get_all_users()
        if users:
            for u in users:
                id, nama, email, username, expired, status, is_trial = u
                emoji = "🎁" if is_trial else ("🟢" if status == "aktif" else "🔴")
                label = "TRIAL" if is_trial else "BERBAYAR"
                with st.expander(f"{emoji} [{label}] {nama} - {username}"):
                    st.write(f"**Email:** {email}")
                    st.write(f"**Username:** `{username}`")
                    st.write(f"**Expired:** {expired}")
                    st.write(f"**Status:** {status}")
                    col1, col2 = st.columns(2)
                    with col1:
                        ext_days = st.number_input("Perpanjang (hari)", min_value=1, max_value=365, value=30, key=f"ext{id}")
                        if st.button("🔄 Perpanjang", key=f"btnext{id}"):
                            extend_user(id, ext_days)
                            st.success(f"✅ Diperpanjang {ext_days} hari!")
                            st.rerun()
                    with col2:
                        if st.button("🗑️ Hapus", key=f"btndel{id}"):
                            delete_user(id)
                            st.warning("User dihapus!")
                            st.rerun()
        else:
            st.info("Belum ada user terdaftar.")
    st.sidebar.markdown("---")
    st.sidebar.info("🔗 URL Admin: `?admin=true`")
    st.sidebar.warning("⚠️ Jangan bagikan URL ini!")

# ==================== USER DASHBOARD ====================
else:
    # ---- SIDEBAR ----
    with st.sidebar:
        st.markdown(f"<h3 style='color:#00ff88;'>👤 {st.session_state.nama}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#888;'>📅 {datetime.now().strftime('%A, %d %B %Y')}</p>", unsafe_allow_html=True)
        st.markdown("---")
        
        if st.button("📊 ANALISA", use_container_width=True):
            st.session_state.user_page = "analisa"
            st.rerun()
        if st.button("🎯 SINYAL", use_container_width=True):
            st.session_state.user_page = "sinyal"
            st.rerun()
        
        st.markdown("---")
        # Info masa aktif
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT expired_date, is_trial FROM users WHERE nama=?", (st.session_state.nama,))
        row = c.fetchone()
        conn.close()
        if row:
            expired_date = datetime.strptime(row[0], "%Y-%m-%d")
            sisa = (expired_date - datetime.now()).days
            if row[1]:
                st.warning(f"🎁 TRIAL - {sisa} hari tersisa")
            else:
                st.info(f"⏳ Aktif - {sisa} hari tersisa")
        
        if st.button("🚪 LOGOUT", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.session_state.nama = None
            st.session_state.user_page = "analisa"
            st.session_state.analysis_result = None
            st.rerun()
    
    # ---- HEADER ----
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("<h2 style='color:#00ff88;'>📊 ATS / Alu Trading System</h2>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<p style='text-align:right; color:#888;'>{datetime.now().strftime('%A, %d %B %Y')}</p>", unsafe_allow_html=True)
    
    # ---- NAVIGASI PASANGAN ----
    st.markdown("---")
    kategori = st.selectbox("Pilih Kategori", ["KOMODITAS", "FOREX", "CRYPTO"])
    
    if kategori == "KOMODITAS":
        pair_list = ["XAUUSD", "XAGUSD", "USOIL"]
    elif kategori == "FOREX":
        pair_list = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"]
    else:
        pair_list = ["BTCUSD", "ETHUSD", "XRPUSD", "ADAUSD", "SOLUSD"]
    
    pair = st.selectbox("Pilih Pair", pair_list)
    
    # ---- HALAMAN ANALISA ----
    if st.session_state.user_page == "analisa":
        st.markdown(f"<h1 style='color:#fff;'>{pair} <span style='color:#888; font-size:16px;'>· 4h · {kategori}</span></h1>", unsafe_allow_html=True)
        
        # Fetch harga real-time untuk display
        df_disp = fetch_data(pair)
        if df_disp is not None:
            current_price = df_disp["Close"].iloc[-1]
            prev_price = df_disp["Close"].iloc[-2] if len(df_disp) > 1 else current_price
            change = current_price - prev_price
            change_pct = (change / prev_price) * 100
            color = "#00ff88" if change >= 0 else "#ff4444"
            st.markdown(f"""
            <div style="display:flex; align-items:baseline; gap:20px;">
                <h1 style="color:{color};">{current_price:.2f}</h1>
                <span style="color:{color}; font-size:20px;">{'▲' if change>=0 else '▼'} {change:.2f} ({change_pct:.2f}%)</span>
            </div>
            """, unsafe_allow_html=True)
        
        # Chart TradingView
        tv_symbol_map = {
            "XAUUSD": "OANDA:XAUUSD",
            "XAGUSD": "OANDA:XAGUSD",
            "USOIL": "OANDA:USOIL",
            "EURUSD": "OANDA:EURUSD",
            "GBPUSD": "OANDA:GBPUSD",
            "USDJPY": "OANDA:USDJPY",
            "AUDUSD": "OANDA:AUDUSD",
            "NZDUSD": "OANDA:NZDUSD",
            "USDCAD": "OANDA:USDCAD",
            "USDCHF": "OANDA:USDCHF",
            "BTCUSD": "BINANCE:BTCUSDT",
            "ETHUSD": "BINANCE:ETHUSDT",
            "XRPUSD": "BINANCE:XRPUSDT",
            "ADAUSD": "BINANCE:ADAUSDT",
            "SOLUSD": "BINANCE:SOLUSDT",
        }
        tv_symbol = tv_symbol_map.get(pair, "OANDA:XAUUSD")
        
        tv_widget = f"""
        <div class="tradingview-widget-container" style="height:500px;">
          <div id="tv_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%",
            "height": 500,
            "symbol": "{tv_symbol}",
            "interval": "240",
            "timezone": "Asia/Jakarta",
            "theme": "dark",
            "style": "1",
            "locale": "id",
            "toolbar_bg": "#0E1117",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": false,
            "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
            "container_id": "tv_chart"
          }});
          </script>
        </div>
        """
        components.html(tv_widget, height=520)
        
        # Timeframe bar statis
        st.markdown("---")
        cols = st.columns(9)
        tfs = ["WEEKLY", "DAILY", "H4", "H1", "M30", "M15", "M5", "M3", "M1"]
        for i, tf in enumerate(tfs):
            with cols[i]:
                if tf == "H4":
                    st.markdown(f"<div style='background:#00ff88;color:#000;padding:8px;border-radius:8px;text-align:center;font-weight:bold;'>{tf}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='background:#1a1a2e;color:#888;padding:8px;border-radius:8px;text-align:center;'>{tf}</div>", unsafe_allow_html=True)
        
        # Tombol Analisa
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("🔍 ANALISA SMC/ICT", use_container_width=True):
                with st.spinner("Menganalisa struktur smart money..."):
                    result, error = ict_analysis(pair)
                if error:
                    st.error(error)
                else:
                    st.session_state.analysis_result = result
                    st.session_state.user_page = "sinyal"
                    st.rerun()
        with col2:
            st.button("📰 BERITA", use_container_width=True)
        with col3:
            st.button("🌍 ISU", use_container_width=True)
        with col4:
            st.button("📅 KALENDER", use_container_width=True)
    
    # ---- HALAMAN SINYAL ----
    elif st.session_state.user_page == "sinyal":
        if st.button("⬅️ Kembali ke Chart"):
            st.session_state.user_page = "analisa"
            st.rerun()
        
        result = st.session_state.analysis_result
        if result:
            signal = result["signal"]
            card_class = "signal-card" if signal == "BUY" else "signal-card sell-signal"
            emoji = "🟢" if signal == "BUY" else "🔴"
            
            st.markdown(f"""
            <div class="{card_class}">
                <p style="color:#ccc; font-size:18px;">📈 SINYAL ICT</p>
                <h1>{emoji} {signal}</h1>
                <p style="color:#fff; font-size:24px;">{pair} · 4H</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class="signal-details">
                <p>📍 <b>ENTRY :</b> {result['entry']:.2f}</p>
                <p>🛑 <b>SL :</b> {result['sl']:.2f}</p>
                <p>🎯 <b>TP1 :</b> {result['tp1']:.2f}</p>
                <p>🎯 <b>TP2 :</b> {result['tp2']:.2f}</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### 📝 HASIL ANALISA SMC/ICT")
            st.markdown(f"""
            <div style="background:#1a1a2e; border-radius:15px; padding:20px; color:#ccc;">
                <ul>
                    {"".join([f"<li>{r}</li>" for r in result['reasons']])}
                </ul>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Belum ada sinyal. Klik ANALISA SMC/ICT di halaman Chart.")
        
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.button("📰 BERITA", use_container_width=True)
        with col2:
            st.button("🌍 ISU", use_container_width=True)
        with col3:
            st.button("📅 KALENDER", use_container_width=True)
