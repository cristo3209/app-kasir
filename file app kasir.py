import streamlit as st
import pandas as pd
import plotly.express as px
import qrcode
from PIL import Image
import io
from datetime import datetime
import sqlite3

# ------------------------------
# Koneksi & Setup Database
# ------------------------------
DB_NAME = "kasir.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total INTEGER NOT NULL,
            metode TEXT NOT NULL,
            status TEXT NOT NULL,
            kartu_akhir TEXT
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
    conn.close()

def insert_transaction(timestamp, total, metode, status, items, kartu_akhir=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (timestamp, total, metode, status, kartu_akhir)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, total, metode, status, kartu_akhir))
    trans_id = c.lastrowid
    for item in items:
        c.execute('''
            INSERT INTO transaction_items (transaction_id, nama, harga, qty)
            VALUES (?, ?, ?, ?)
        ''', (trans_id, item["nama"], item["harga"], item["qty"]))
    conn.commit()
    conn.close()
    return trans_id

def get_all_transactions():
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM transactions ORDER BY id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_transaction_items(trans_id):
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM transaction_items WHERE transaction_id = ?"
    df = pd.read_sql_query(query, conn, params=(trans_id,))
    conn.close()
    return df

# Inisialisasi database
init_db()

# ------------------------------
# Inisialisasi Session State (hanya untuk keranjang)
# ------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []

# ------------------------------
# Data Produk Dummy
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
# Fungsi Bantu
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
st.markdown("Simulasi Pembayaran via **Xendit** — QRIS, DuitNow QR, Kartu Kredit (data tersimpan di SQLite)")

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
            ["QRIS", "DuitNow QR", "Kartu Kredit"],
            key="metode"
        )

        if metode in ["QRIS", "DuitNow QR"]:
            st.subheader(f"📱 Bayar dengan {metode}")
            qr_string = f"XENDIT|{metode}|INV-TEMP|Rp{total}"
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
                st.session_state.cart = []
                st.success(f"Pembayaran berhasil! Transaksi #{trans_id} disimpan ke database.")
                st.rerun()

        else:
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
                        st.session_state.cart = []
                        st.success(f"Pembayaran kartu kredit berhasil! Transaksi #{trans_id} disimpan.")
                        st.rerun()
                    else:
                        st.error("Mohon isi semua data kartu dengan benar (16 digit nomor, 3 digit CVV).")
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
            st.dataframe(df_trans.drop(columns=["id", "kartu_akhir"], errors="ignore").tail(10), use_container_width=True)
            selected_id = st.selectbox("Lihat detail item transaksi ID:", df_trans["id"].tolist())
            if selected_id:
                detail = get_transaction_items(selected_id)
                st.dataframe(detail[["nama", "harga", "qty"]], use_container_width=True)