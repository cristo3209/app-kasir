import streamlit as st
import pandas as pd
import qrcode
from PIL import Image
import io
from datetime import datetime
import sqlite3
import traceback
import os

# ------------------------------
# Database di /tmp agar writable
# ------------------------------
DB_PATH = "/tmp/kasir.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS transactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT,
                      total INTEGER,
                      metode TEXT,
                      status TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transaction_items
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      transaction_id INTEGER,
                      nama TEXT,
                      harga INTEGER,
                      qty INTEGER,
                      FOREIGN KEY(transaction_id) REFERENCES transactions(id))''')
        conn.commit()
    except Exception as e:
        st.error(f"❌ Gagal inisialisasi DB: {traceback.format_exc()}")
    finally:
        conn.close()

def save_transaction(total, metode, items):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO transactions (timestamp, total, metode, status) VALUES (?,?,?,?)",
                  (timestamp, total, metode, "Sukses"))
        trans_id = c.lastrowid
        for item in items:
            c.execute("INSERT INTO transaction_items (transaction_id, nama, harga, qty) VALUES (?,?,?,?)",
                      (trans_id, item["nama"], item["harga"], item["qty"]))
        conn.commit()
        return trans_id
    except Exception as e:
        st.error(f"❌ Gagal menyimpan transaksi:\n{traceback.format_exc()}")
        return None
    finally:
        if conn:
            conn.close()

def generate_qr(data: str):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()

# ------------------------------
# Mulai aplikasi
# ------------------------------
st.set_page_config(page_title="Kasir QRIS", layout="centered")
st.title("🧾 Kasir - QRIS Payment (Simulasi Xendit)")

# Inisialisasi database
init_db()

# Session keranjang
if "cart" not in st.session_state:
    st.session_state.cart = []

# Daftar produk
produk_list = [
    {"nama": "Nasi Goreng", "harga": 15000},
    {"nama": "Mie Goreng", "harga": 12000},
    {"nama": "Ayam Bakar", "harga": 20000},
    {"nama": "Es Teh", "harga": 5000},
    {"nama": "Es Jeruk", "harga": 7000},
    {"nama": "Kopi", "harga": 10000},
]

# Form pilih produk
with st.form("order_form"):
    st.subheader("📋 Pilih Produk")
    qty_input = {}
    cols = st.columns(3)
    for i, p in enumerate(produk_list):
        with cols[i % 3]:
            qty = st.number_input(f"{p['nama']} (Rp{p['harga']:,})", 0, 20, 0, key=p['nama'])
            qty_input[p['nama']] = {"harga": p['harga'], "qty": qty}

    if st.form_submit_button("➕ Tambahkan ke Keranjang"):
        st.session_state.cart = []
        for nama, info in qty_input.items():
            if info["qty"] > 0:
                st.session_state.cart.append({"nama": nama, "harga": info["harga"], "qty": info["qty"]})
        st.success("Keranjang diupdate!")
        st.rerun()

# Tampilkan keranjang
if st.session_state.cart:
    total = sum(item["harga"] * item["qty"] for item in st.session_state.cart)
    st.subheader("🛒 Keranjang Anda")
    for item in st.session_state.cart:
        st.write(f"- {item['nama']} x{item['qty']} = Rp{item['harga'] * item['qty']:,}")
    st.markdown(f"### Total: **Rp{total:,}**")

    # QRIS Section
    st.markdown("---")
    st.subheader("📱 Bayar dengan QRIS")
    qr_data = f"XENDIT|QRIS|{datetime.now().timestamp()}|Rp{total}"
    qr_image = generate_qr(qr_data)
    st.image(qr_image, caption="Scan QRIS untuk membayar", width=300)

    if st.button("✅ Selesaikan Pembayaran QRIS", type="primary"):
        # Cek apakah DB bisa diakses
        if not os.path.exists(DB_PATH):
            st.error("Database belum terinisialisasi. Refresh halaman.")
        else:
            trans_id = save_transaction(total, "QRIS", st.session_state.cart)
            if trans_id:
                st.session_state.cart = []
                st.success(f"✅ Pembayaran sukses! Transaksi #{trans_id} tercatat.")
                st.balloons()
                st.rerun()
            else:
                st.error("Transaksi gagal, lihat pesan error di atas.")
else:
    st.info("Silakan pilih produk dan tambahkan ke keranjang.")
