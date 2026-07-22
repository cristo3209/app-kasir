import streamlit as st
import pandas as pd
import plotly.express as px
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
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total INTEGER NOT NULL,
                metode TEXT NOT NULL,
                status TEXT NOT NULL,
                kartu_akhir TEXT,
                gopay_phone TEXT
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
        conn.commit()
    except Exception as e:
        st.error(f"❌ Gagal inisialisasi database: {traceback.format_exc()}")
    finally:
        conn.close()

def insert_transaction(timestamp, total, metode, status, items, kartu_akhir=None, gopay_phone=None):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO transactions (timestamp, total, metode, status, kartu_akhir, gopay_phone)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (timestamp, total, metode, status, kartu_akhir, gopay_phone))
        trans_id = c.lastrowid
        for item in items:
            c.execute('''
                INSERT INTO transaction_items (transaction_id, nama, harga, qty)
                VALUES (?, ?, ?, ?)
            ''', (trans_id, item["nama"], item["harga"], item["qty"]))
        conn.commit()
        return trans_id
    except Exception as e:
        st.error(f"❌ Gagal menyimpan transaksi: {traceback.format_exc()}")
        return None
    finally:
        if conn:
            conn.close()

def get_all_transactions():
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM transactions ORDER BY id DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Gagal membaca transaksi: {e}")
        return pd.DataFrame()

def get_transaction_items(trans_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM transaction_items WHERE transaction_id = ?"
        df = pd.read_sql_query(query, conn, params=(trans_id,))
        conn.close()
        return df
    except Exception as e:
        st.error(f"Gagal membaca item transaksi: {e}")
        return pd.DataFrame()

# Inisialisasi database
init_db()

# ------------------------------
# Session keranjang
# ------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []

# ------------------------------
# Data Produk
# ------------------------------
PRODUK = [
    {"nama": "Nasi Goreng", "harga": 15000},
    {"nama": "Mie Goreng", "harga": 12000},
    {"nama": "Ayam Bakar", "harga": 20000},
    {"nama": "Es Teh", "harga": 5000},
    {"nama": "Es Jeruk", "harga": 7000},
    {"nama": "Kopi", "harga": 10000},
]

# ------------------------------
# Fungsi QR
# ------------------------------
def generate_qr(data: str):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()

# ------------------------------
# UI Utama
# ------------------------------
st.set_page_config(page_title="Kasir & Dashboard", layout="wide")
st.title("🧾 Aplikasi Kasir + Dashboard")
st.markdown("Simulasi Pembayaran via **Xendit** — QRIS, DuitNow QR, GoPay, Kartu Kredit, Cash")

tab1, tab2 = st.tabs(["🛒 Kasir", "📊 Dashboard"])

# ======================
# TAB KASIR
# ======================
with tab1:
    st.header("Pilih Produk & Bayar")

    with st.form("produk_form"):
        st.subheader("Menu Makanan & Minuman")
        items_input = {}
        cols = st.columns(3)
        for i, p in enumerate(PRODUK):
            with cols[i % 3]:
                qty = st.number_input(
                    f"{p['nama']} (Rp{p['harga']:,})",
                    min_value=0, value=0, step=1,
                    key=f"qty_{p['nama']}"
                )
                items_input[p['nama']] = {"harga": p['harga'], "qty": qty}

        submitted = st.form_submit_button("➕ Tambahkan ke Keranjang")
        if submitted:
            st.session_state.cart = []
            for nama, data in items_input.items():
                if data["qty"] > 0:
                    st.session_state.cart.append({
                        "nama": nama,
                        "harga": data["harga"],
                        "qty": data["qty"]
                    })
            st.success("Keranjang berhasil diperbarui!")
            st.rerun()

    if st.session_state.cart:
        st.subheader("🛍️ Keranjang Belanja")
        total = sum(item["harga"] * item["qty"] for item in st.session_state.cart)
        for item in st.session_state.cart:
            st.write(f"- {item['nama']} x {item['qty']} = Rp{item['harga']*item['qty']:,}")
        st.markdown(f"### Total: **Rp{total:,}**")

        st.markdown("---")
        metode = st.radio(
            "💳 Metode Pembayaran",
            ["QRIS", "DuitNow QR", "GoPay", "Kartu Kredit", "Cash"],
            key="metode"
        )

        # ========== QRIS / DuitNow QR ==========
        if metode in ["QRIS", "DuitNow QR"]:
            st.subheader(f"📱 Bayar dengan {metode}")
            qr_string = f"XENDIT|{metode}|{datetime.now().timestamp()}|Rp{total}"
            qr_bytes = generate_qr(qr_string)
            st.image(qr_bytes, caption=f"Scan {metode} untuk membayar Rp{total:,}", width=300)

            if st.button("✅ Selesaikan Pembayaran", key="bayar_qr"):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trans_id = insert_transaction(
                    timestamp=timestamp,
                    total=total,
                    metode=metode,
                    status="Sukses",
                    items=st.session_state.cart
                )
                if trans_id is not None:
                    st.session_state.cart = []
                    st.success(f"Pembayaran {metode} berhasil! Transaksi #{trans_id} disimpan.")
                    st.rerun()
                else:
                    st.error("Transaksi gagal. Cek pesan error di atas.")

        # ========== GoPay ==========
        elif metode == "GoPay":
            st.subheader("📱 Bayar dengan GoPay")
            gopay_phone = st.text_input("Nomor HP terdaftar di GoPay", max_chars=13, placeholder="081234567890")
            qr_string = f"GOPAY|{gopay_phone}|{datetime.now().timestamp()}|Rp{total}"
            qr_bytes = generate_qr(qr_string)
            st.image(qr_bytes, caption=f"Scan QR untuk bayar dengan GoPay Rp{total:,}", width=300)

            if st.button("✅ Selesaikan Pembayaran GoPay", key="bayar_gopay"):
                if gopay_phone and len(gopay_phone) >= 10:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    trans_id = insert_transaction(
                        timestamp=timestamp,
                        total=total,
                        metode="GoPay",
                        status="Sukses",
                        items=st.session_state.cart,
                        gopay_phone=gopay_phone
                    )
                    if trans_id is not None:
                        st.session_state.cart = []
                        st.success(f"Pembayaran GoPay berhasil! Transaksi #{trans_id} disimpan.")
                        st.rerun()
                else:
                    st.error("Nomor HP tidak valid (minimal 10 digit).")

        # ========== Kartu Kredit ==========
        elif metode == "Kartu Kredit":
            st.subheader("💳 Detail Kartu Kredit")
            with st.form("kartu_form"):
                nomor = st.text_input("Nomor Kartu (16 digit)", max_chars=16, placeholder="1234567812345678")
                nama = st.text_input("Nama Pemegang Kartu")
                exp = st.text_input("Tanggal Kadaluarsa (MM/YY)", max_chars=5, placeholder="MM/YY")
                cvv = st.text_input("CVV", max_chars=3, type="password")
                submit_kartu = st.form_submit_button("Bayar dengan Kartu Kredit")

                if submit_kartu:
                    if nomor and nama and exp and cvv and len(nomor) == 16 and len(cvv) == 3:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        trans_id = insert_transaction(
                            timestamp=timestamp,
                            total=total,
                            metode="Kartu Kredit",
                            status="Sukses",
                            items=st.session_state.cart,
                            kartu_akhir=nomor[-4:]
                        )
                        if trans_id is not None:
                            st.session_state.cart = []
                            st.success(f"Pembayaran kartu kredit berhasil! Transaksi #{trans_id} disimpan.")
                            st.rerun()
                    else:
                        st.error("Mohon isi semua data kartu dengan benar (16 digit nomor, 3 digit CVV).")

        # ========== Cash ==========
        else:  # Cash
            st.subheader("💵 Pembayaran Cash")
            st.write(f"Total yang harus dibayar: **Rp{total:,}**")
            uang_dibayar = st.number_input("Jumlah uang diterima (Rp)", min_value=0, value=0, step=1000)
            if uang_dibayar >= total and total > 0:
                kembalian = uang_dibayar - total
                st.write(f"Kembalian: **Rp{kembalian:,}**")
                if st.button("✅ Selesaikan Pembayaran Cash", key="bayar_cash"):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    trans_id = insert_transaction(
                        timestamp=timestamp,
                        total=total,
                        metode="Cash",
                        status="Sukses",
                        items=st.session_state.cart
                    )
                    if trans_id is not None:
                        st.session_state.cart = []
                        st.success(f"Pembayaran cash berhasil! Transaksi #{trans_id} disimpan.")
                        st.rerun()
            elif total > 0:
                st.warning("Jumlah uang yang diterima kurang dari total belanja.")
    else:
        st.info("🛒 Keranjang masih kosong. Silakan pilih produk dan klik 'Tambahkan ke Keranjang'.")

# ======================
# TAB DASHBOARD
# ======================
with tab2:
    st.header("📊 Dashboard Analisis Penjualan")

    df_trans = get_all_transactions()

    if df_trans.empty:
        st.info("Belum ada data transaksi. Lakukan pembayaran di tab Kasir terlebih dahulu.")
    else:
        total_omset = df_trans["total"].sum()
        st.metric(label="💰 Total Omset", value=f"Rp{total_omset:,.0f}")

        st.subheader("🏆 Produk Terlaris")
        all_items = []
        for trans_id in df_trans["id"]:
            items_df = get_transaction_items(trans_id)
            if not items_df.empty:
                all_items.append(items_df)
        if all_items:
            df_items = pd.concat(all_items)
            df_produk = df_items.groupby("nama")["qty"].sum().reset_index()
            df_produk = df_produk.sort_values("qty", ascending=False)
            fig_bar = px.bar(
                df_produk, x="nama", y="qty",
                title="Jumlah Produk Terjual",
                labels={"qty": "Jumlah", "nama": "Produk"},
                color="nama"
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.write("Tidak ada item terjual.")

        st.subheader("📌 Proporsi Metode Pembayaran")
        metode_counts = df_trans["metode"].value_counts().reset_index()
        metode_counts.columns = ["Metode", "Jumlah Transaksi"]
        fig_pie = px.pie(
            metode_counts, values="Jumlah Transaksi", names="Metode",
            title="Metode Pembayaran (Jumlah Transaksi)",
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        with st.expander("📋 Lihat Riwayat Transaksi"):
            st.dataframe(df_trans.drop(columns=["id", "kartu_akhir", "gopay_phone"], errors="ignore").tail(10), use_container_width=True)
            selected_id = st.selectbox("Lihat detail item transaksi ID:", df_trans["id"].tolist())
            if selected_id:
                detail = get_transaction_items(selected_id)
                st.dataframe(detail[["nama", "harga", "qty"]], use_container_width=True)
