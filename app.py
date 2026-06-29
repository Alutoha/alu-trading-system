import streamlit as st
import sqlite3
import bcrypt
import random
import string
from datetime import datetime, timedelta

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
            status TEXT DEFAULT 'aktif'
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

def generate_user(nama, email, masa_hari):
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
            "INSERT INTO users (nama, email, username, password_hash, expired_date) VALUES (?, ?, ?, ?, ?)",
            (nama, email, username, hashed, expired)
        )
        conn.commit()
        conn.close()
        return username, password, expired
    except sqlite3.IntegrityError:
        conn.close()
        return generate_user(nama, email, masa_hari)

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nama, email, username, expired_date, status FROM users ORDER BY id DESC")
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

# ==================== SESSION ====================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None
if "nama" not in st.session_state:
    st.session_state.nama = None

# ==================== MAIN APP ====================
st.set_page_config(page_title="Alu Trading System", page_icon="🔐", layout="centered")
init_db()

if not st.session_state.logged_in:
    st.title("🔐 Alu Trading System")
    st.subheader("Silakan Login")
    
    role = st.radio("Login sebagai:", ["User", "Admin"], horizontal=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("🔓 MASUK", use_container_width=True):
        if role == "Admin":
            if verify_admin(username, password):
                st.session_state.logged_in = True
                st.session_state.role = "admin"
                st.rerun()
            else:
                st.error("❌ Username atau password admin salah!")
        else:
            nama, error = verify_user(username, password)
            if nama:
                st.session_state.logged_in = True
                st.session_state.role = "user"
                st.session_state.nama = nama
                st.rerun()
            else:
                st.error(f"❌ {error}")
    
    st.info("🔑 Admin default: username=admin, password=admin123")

elif st.session_state.role == "admin":
    st.sidebar.success("👑 Admin Mode")
    
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()
    
    st.title("👑 Alu Trading System - Admin Panel")
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["➕ Generate Kode", "📋 Daftar User"])
    
    with tab1:
        st.subheader("Generate Kode Akses Baru")
        
        col1, col2 = st.columns(2)
        with col1:
            nama = st.text_input("Nama", placeholder="Adi")
        with col2:
            email = st.text_input("Email", placeholder="adi@gmail.com")
        
        masa_aktif = st.selectbox("Masa Aktif", [7, 30, 90, 180, 365], format_func=lambda x: f"{x} Hari")
        
        if st.button("🔑 GENERATE KODE", use_container_width=True):
            if nama and email:
                username, password, expired = generate_user(nama, email, masa_aktif)
                st.success("✅ Kode akses berhasil dibuat!")
                st.markdown(f"""
                ### 📋 Detail Akses:
                - **Username:** `{username}`
                - **Password:** `{password}`
                - **Expired:** `{expired}`
                
                > ⚠️ Simpan password ini! Tidak bisa dilihat lagi.
                """)
            else:
                st.error("Mohon isi nama dan email!")
    
    with tab2:
        st.subheader("Daftar User Terdaftar")
        users = get_all_users()
        
        if users:
            for u in users:
                id, nama, email, username, expired, status = u
                emoji = "🟢" if status == "aktif" else "🔴"
                
                with st.expander(f"{emoji} {nama} - {username}"):
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

else:
    st.sidebar.success(f"👤 {st.session_state.nama}")
    
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.nama = None
        st.rerun()
    
    st.title(f"👋 Selamat Datang, {st.session_state.nama}!")
    st.markdown("---")
    st.info("🚧 Dashboard Alu Trading System - Analisa XAUUSD segera hadir.")
    st.markdown("### 📊 Market Watch")
    st.metric("XAUUSD", "$2,345.67", "▲ 0.8%")
    st.success("🔜 AI Signal Generator coming soon...")
