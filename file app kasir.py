import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import traceback
import os
import hashlib

# ------------------------------
# Database
# ------------------------------
DB_PATH = "/tmp/kasir.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Tabel transaksi
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total INTEGER NOT NULL,
                metode TEXT NOT NULL,
                status TEXT NOT NULL,
                keterangan TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS transaction_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                nama TEXT NOT NULL,
                harga INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions (id)
            )
        ''')
        
        # Tabel settings
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # PIN default: 000000
        default_pin_hash = hashlib.sha256("000000".encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('pin_hash', ?)", 
                 (default_pin_hash,))
        # Recovery code default
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('recovery_code', ?)", 
                 ("ADMIN123",))
        
        conn.commit()
    except Exception as e:
        st.error(f"❌ DB init error: {traceback.format_exc()}")
    finally:
        conn.close()

def get_setting(key):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None

def update_setting(key, value):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Gagal update setting: {e}")
        return False

def verify_pin(pin_input):
    stored_hash = get_setting("pin_hash")
    input_hash = hashlib.sha256(pin_input.encode()).hexdigest()
    return stored_hash == input_hash

def change_pin(new_pin):
    new_hash = hashlib.sha256(new_pin.encode()).hexdigest()
    return update_setting("pin_hash", new_hash)

def insert_transaction(timestamp, total, metode, status, items, keterangan=None):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO transactions (timestamp, total, metode, status, keterangan)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, total, metode, status, keterangan))
        trans_id = c.lastrowid
        for item in items:
            c.execute('''
                INSERT INTO transaction_items (transaction_id, nama, harga, qty)
                VALUES (?, ?, ?, ?)
            ''', (trans_id, item["nama"], item["harga"], item["qty"]))
        conn.commit()
        return trans_id
    except Exception as e:
        st.error(f"❌ Gagal simpan: {traceback.format_exc()}")
        return None
    finally:
        if conn:
            conn.close()

def get_all_transactions():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

def get_transaction_items(trans_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM transaction_items WHERE transaction_id = ?", conn, params=(trans_id,))
        conn.close()
        return df
    except:
        return pd.DataFrame()

init_db()

# ------------------------------
# Session State
# ------------------------------
if "owner_authenticated" not in st.session_state:
    st.session_state.owner_authenticated = False
if "cart" not in st.session_state:
    st.session_state.cart = []
if "show_reset" not in st.session_state:
    st.session_state.show_reset = False
if "show_change_pin" not in st.session_state:
    st.session_state.show_change_pin = False

# ------------------------------
# UI Utama
# ------------------------------
st.set_page_config(page_title="Kasir & Dashboard", layout="wide")
st.title("🧾 Aplikasi Kasir + Dashboard")

PRODUK = [
    {"nama": "Nasi Goreng", "harga": 15000},
    {"nama": "Mie Goreng", "harga": 12000},
    {"nama": "Ayam Bakar", "harga": 20000},
    {"nama": "Es Teh", "harga": 5000},
    {"nama": "Es Jeruk", "harga": 7000},
    {"nama": "Kopi", "harga": 10000},
]

tab1, tab2 = st.tabs(["🛒 Kasir (Karyawan)", "🔐 Dashboard (Owner)"])

# ======================
# TAB KASIR
# ======================
with tab1:
    st.header("🧑‍🍳 Kasir")
    with st.form("produk_form"):
        st.subheader("Menu")
        items_input = {}
        cols = st.columns(3)
        for i, p in enumerate(PRODUK):
            with cols[i % 3]:
                qty = st.number_input(f"{p['nama']} (Rp{p['harga']:,})", 0, 20, 0, key=f"qty_{p['nama']}")
                items_input[p['nama']] = {"harga": p['harga'], "qty": qty}
        if st.form_submit_button("➕ Tambahkan ke Keranjang"):
            st.session_state.cart = []
            for nama, data in items_input.items():
                if data["qty"] > 0:
                    st.session_state.cart.append({"nama": nama, "harga": data["harga"], "qty": data["qty"]})
            st.success("Keranjang diperbarui!")
            st.rerun()

    if st.session_state.cart:
        st.subheader("🛒 Keranjang")
        total = sum(item["harga"] * item["qty"] for item in st.session_state.cart)
        for item in st.session_state.cart:
            st.write(f"- {item['nama']} x{item['qty']} = Rp{item['harga']*item['qty']:,}")
        st.markdown(f"### Total: **Rp{total:,}**")
        metode = st.radio("💳 Metode Pembayaran", ["QRIS", "DuitNow QR", "GoPay", "Kartu Kredit", "Cash"])

        if metode in ["QRIS", "DuitNow QR", "GoPay", "Kartu Kredit"]:
            st.info(f"Pembayaran via **{metode}**.")
            if st.button("✅ Selesaikan Pembayaran", key="noncash"):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trans_id = insert_transaction(timestamp, total, metode, "Sukses", st.session_state.cart, f"Pembayaran {metode}")
                if trans_id:
                    st.session_state.cart = []
                    st.success(f"Transaksi #{trans_id} berhasil.")
                    st.rerun()
        else:
            st.subheader("💵 Cash")
            uang = st.number_input("Uang diterima (Rp)", 0, step=1000)
            if uang >= total > 0:
                kembalian = uang - total
                st.write(f"Kembalian: **Rp{kembalian:,}**")
                if st.button("✅ Selesaikan Pembayaran Cash"):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    trans_id = insert_transaction(timestamp, total, "Cash", "Sukses", st.session_state.cart, f"Cash Rp{uang:,}, kembali Rp{kembalian:,}")
                    if trans_id:
                        st.session_state.cart = []
                        st.success(f"Transaksi #{trans_id} berhasil.")
                        st.rerun()
            elif total > 0:
                st.warning("Uang kurang.")
    else:
        st.info("Keranjang kosong.")

# ======================
# TAB DASHBOARD (OWNER)
# ======================
with tab2:
    st.header("📊 Dashboard Owner")

    # ========== MODE LOGIN ==========
    if not st.session_state.owner_authenticated:
        
        # ---- Reset PIN (jika klik Lupa PIN) ----
        if st.session_state.show_reset:
            st.subheader("🔄 Reset PIN")
            st.info("Masukkan kode pemulihan untuk mereset PIN ke 000000.")
            recovery_input = st.text_input("Kode Pemulihan", type="password")
            if st.button("✅ Reset PIN Sekarang"):
                stored_recovery = get_setting("recovery_code")
                if recovery_input == stored_recovery:
                    if change_pin("000000"):
                        st.success("✅ PIN berhasil direset ke 000000. Silakan login dengan PIN 000000.")
                        st.session_state.show_reset = False
                        st.rerun()
                    else:
                        st.error("Gagal mereset PIN.")
                else:
                    st.error("Kode pemulihan salah!")
            if st.button("⬅️ Kembali ke Login"):
                st.session_state.show_reset = False
                st.rerun()
        
        # ---- Login normal ----
        else:
            st.warning("🔐 Masukkan PIN untuk mengakses dashboard.")
            pin_input = st.text_input("PIN (6 digit)", type="password", max_chars=6)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔓 Buka Dashboard", use_container_width=True):
                    if verify_pin(pin_input):
                        st.session_state.owner_authenticated = True
                        st.success("Akses diberikan!")
                        st.rerun()
                    else:
                        st.error("PIN salah!")
            with col2:
                if st.button("❓ Lupa PIN", use_container_width=True):
                    st.session_state.show_reset = True
                    st.rerun()

    # ========== MODE SUDAH LOGIN ==========
    else:
        st.success("✅ Anda terautentikasi sebagai Owner.")
        
        # Tombol Logout
        if st.button("🚪 Logout", key="logout_btn"):
            st.session_state.owner_authenticated = False
            st.session_state.show_change_pin = False
            st.rerun()
        
        st.markdown("---")
        
        # ---- GANTI PIN (expandable) ----
        with st.expander("⚙️ Ganti PIN / Kode Pemulihan"):
            tab_pin, tab_recovery = st.tabs(["🔑 Ganti PIN", "🔄 Ganti Kode Pemulihan"])
            
            with tab_pin:
                st.subheader("Ganti PIN")
                with st.form("change_pin_form"):
                    old_pin = st.text_input("PIN Lama", type="password", max_chars=6)
                    new_pin = st.text_input("PIN Baru (6 digit angka)", type="password", max_chars=6)
                    confirm_pin = st.text_input("Konfirmasi PIN Baru", type="password", max_chars=6)
                    
                    if st.form_submit_button("💾 Simpan PIN Baru"):
                        if not old_pin or not new_pin or not confirm_pin:
                            st.error("Semua field harus diisi!")
                        elif not verify_pin(old_pin):
                            st.error("PIN lama salah!")
                        elif len(new_pin) != 6 or not new_pin.isdigit():
                            st.error("PIN baru harus 6 digit angka!")
                        elif new_pin != confirm_pin:
                            st.error("PIN baru dan konfirmasi tidak cocok!")
                        else:
                            if change_pin(new_pin):
                                st.success("✅ PIN berhasil diubah! Gunakan PIN baru untuk login selanjutnya.")
                            else:
                                st.error("Gagal mengubah PIN.")
            
            with tab_recovery:
                st.subheader("Ganti Kode Pemulihan")
                st.info("Kode pemulihan digunakan jika Anda lupa PIN. Simpan di tempat aman!")
                current_code = get_setting("recovery_code")
                st.text(f"Kode pemulihan saat ini: **{current_code}**")
                
                with st.form("change_recovery_form"):
                    new_recovery = st.text_input("Kode Pemulihan Baru", type="password")
                    pin_confirm = st.text_input("PIN Anda (untuk konfirmasi)", type="password", max_chars=6)
                    
                    if st.form_submit_button("💾 Simpan Kode Baru"):
                        if not new_recovery or not pin_confirm:
                            st.error("Semua field harus diisi!")
                        elif not verify_pin(pin_confirm):
                            st.error("PIN konfirmasi salah!")
                        elif len(new_recovery) < 6:
                            st.error("Kode pemulihan minimal 6 karakter!")
                        else:
                            if update_setting("recovery_code", new_recovery):
                                st.success("✅ Kode pemulihan berhasil diubah!")
                                st.rerun()
                            else:
                                st.error("Gagal mengubah kode pemulihan.")
        
        st.markdown("---")
        
        # ---- DASHBOARD ----
        df = get_all_transactions()
        if df.empty:
            st.info("Belum ada transaksi.")
        else:
            total_omset = df["total"].sum()
            st.metric("💰 Total Omset", f"Rp{total_omset:,}")

            st.subheader("🏆 Produk Terlaris")
            all_items = []
            for tid in df["id"]:
                items = get_transaction_items(tid)
                if not items.empty:
                    all_items.append(items)
            if all_items:
                df_items = pd.concat(all_items)
                df_produk = df_items.groupby("nama")["qty"].sum().reset_index().sort_values("qty", ascending=False)
                fig_bar = px.bar(df_produk, x="nama", y="qty", color="nama", title="Produk Terlaris")
                st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("📌 Proporsi Metode Pembayaran")
            metode_counts = df["metode"].value_counts().reset_index()
            metode_counts.columns = ["Metode", "Jumlah"]
            fig_pie = px.pie(metode_counts, values="Jumlah", names="Metode", title="Proporsi Pembayaran", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

            with st.expander("📋 Riwayat Transaksi"):
                st.dataframe(df.drop(columns=["id"], errors="ignore").tail(10), use_container_width=True)
                tid_pilih = st.selectbox("Detail item transaksi ID:", df["id"].tolist())
                if tid_pilih:
                    detail = get_transaction_items(tid_pilih)
                    st.dataframe(detail[["nama", "harga", "qty"]], use_container_width=True)
