import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import hashlib
import io

# ------------------------------
# Database
# ------------------------------
DB_PATH = "/tmp/kasir.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabel transaksi
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  total INTEGER,
                  tax REAL,
                  grand_total INTEGER,
                  metode TEXT,
                  status TEXT,
                  keterangan TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transaction_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  transaction_id INTEGER,
                  nama TEXT,
                  harga INTEGER,
                  qty INTEGER,
                  FOREIGN KEY(transaction_id) REFERENCES transactions(id))''')
    
    # Tabel menu
    c.execute('''CREATE TABLE IF NOT EXISTS menu
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  nama TEXT UNIQUE,
                  harga INTEGER)''')
    # Insert menu default jika kosong
    c.execute("SELECT COUNT(*) FROM menu")
    if c.fetchone()[0] == 0:
        default_menu = [
            ("Nasi Goreng", 15000),
            ("Mie Goreng", 12000),
            ("Ayam Bakar", 20000),
            ("Es Teh", 5000),
            ("Es Jeruk", 7000),
            ("Kopi", 10000)
        ]
        c.executemany("INSERT INTO menu (nama, harga) VALUES (?, ?)", default_menu)
    
    # Tabel settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    # PIN default
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('pin_hash', ?)",
              (hashlib.sha256("000000".encode()).hexdigest(),))
    # Tax default (%)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tax_rate', '10')")
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def update_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def verify_pin(pin):
    stored = get_setting("pin_hash")
    return stored == hashlib.sha256(pin.encode()).hexdigest()

def change_pin(new_pin):
    new_hash = hashlib.sha256(new_pin.encode()).hexdigest()
    update_setting("pin_hash", new_hash)

def get_menu():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM menu ORDER BY nama", conn)
    conn.close()
    return df

def add_menu_item(nama, harga):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO menu (nama, harga) VALUES (?, ?)", (nama, harga))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_menu_item(id, nama, harga):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE menu SET nama=?, harga=? WHERE id=?", (nama, harga, id))
    conn.commit()
    conn.close()

def delete_menu_item(id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM menu WHERE id=?", (id,))
    conn.commit()
    conn.close()

def insert_transaction(timestamp, total, tax, grand_total, metode, status, items, keterangan=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO transactions (timestamp, total, tax, grand_total, metode, status, keterangan)
                 VALUES (?,?,?,?,?,?,?)''',
              (timestamp, total, tax, grand_total, metode, status, keterangan))
    trans_id = c.lastrowid
    for item in items:
        c.execute("INSERT INTO transaction_items (transaction_id, nama, harga, qty) VALUES (?,?,?,?)",
                  (trans_id, item["nama"], item["harga"], item["qty"]))
    conn.commit()
    conn.close()
    return trans_id

def get_all_transactions():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
    conn.close()
    return df

def get_transaction_items(trans_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM transaction_items WHERE transaction_id = ?", conn, params=(trans_id,))
    conn.close()
    return df

# Inisialisasi database
init_db()

# ------------------------------
# Session State
# ------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "cart" not in st.session_state:
    st.session_state.cart = []
if "tax_rate" not in st.session_state:
    st.session_state.tax_rate = float(get_setting("tax_rate") or 10)
if "show_struk" not in st.session_state:
    st.session_state.show_struk = False
if "last_transaction" not in st.session_state:
    st.session_state.last_transaction = None

# ------------------------------
# UI: Halaman Login (jika belum login)
# ------------------------------
if not st.session_state.logged_in:
    st.set_page_config(page_title="Login Kasir", page_icon="🔐")
    st.title("🔐 Akses Kasir")
    with st.form("login_form"):
        pin = st.text_input("Masukkan PIN", type="password", max_chars=6)
        if st.form_submit_button("Masuk"):
            if verify_pin(pin):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("PIN salah!")
    st.stop()

# ==============================
# SETELAH LOGIN
# ==============================
st.set_page_config(page_title="Kasir & Dashboard", layout="wide")
st.title("🧾 Kasir & Dashboard")

# Sidebar logout dan info
with st.sidebar:
    st.write(f"✅ Login berhasil")
    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.cart = []
        st.rerun()
    st.markdown("---")
    st.subheader("⚙️ Pengaturan")
    st.session_state.tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=st.session_state.tax_rate)
    if st.button("Simpan Tax Default"):
        update_setting("tax_rate", str(st.session_state.tax_rate))
        st.success("Tax rate disimpan!")

# Ambil data menu dari DB
menu_df = get_menu()
PRODUK = menu_df.to_dict('records')

tab1, tab2, tab3 = st.tabs(["🛒 Kasir", "📊 Dashboard", "📋 Kelola Menu"])

# ====================== TAB KASIR ======================
with tab1:
    st.header("Transaksi Baru")

    # Tampilkan struk jika ada
    if st.session_state.show_struk and st.session_state.last_transaction:
        trans = st.session_state.last_transaction
        items = trans['items']
        st.subheader("🧾 Struk Pembayaran")
        struk_html = f"""
        <div style="border:1px solid #ccc; padding:15px; border-radius:10px; max-width:400px; margin:auto; font-family:monospace;">
            <h3 style="text-align:center;">STRUK PEMBAYARAN</h3>
            <p style="text-align:center;">{trans['timestamp']}</p>
            <hr>
            <table style="width:100%;">
        """
        for item in items:
            subtotal = item['harga'] * item['qty']
            struk_html += f"<tr><td>{item['nama']} x{item['qty']}</td><td style='text-align:right;'>Rp{subtotal:,}</td></tr>"
        struk_html += f"""
            </table>
            <hr>
            <p>Subtotal: <b>Rp{trans['total']:,}</b></p>
            <p>Tax ({trans['tax_rate']:.1f}%): <b>Rp{int(trans['tax']):,}</b></p>
            <h3>Total: <b>Rp{trans['grand_total']:,}</b></h3>
            <p>Metode: <b>{trans['metode']}</b></p>
            <p>Status: <b>{trans['status']}</b></p>
        </div>
        """
        st.components.v1.html(struk_html, height=400, scrolling=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🖨️ Cetak Struk", use_container_width=True):
                st.components.v1.html(f"<script>window.print();</script>")
        with col2:
            if st.button("✅ Selesai", use_container_width=True):
                st.session_state.show_struk = False
                st.session_state.last_transaction = None
                st.rerun()
    else:
        # Pilih produk
        st.subheader("Menu")
        items_input = {}
        cols = st.columns(3)
        for i, p in enumerate(PRODUK):
            with cols[i % 3]:
                qty = st.number_input(f"{p['nama']} (Rp{p['harga']:,})", 0, 20, 0, key=f"qty_{p['id']}")
                items_input[p['id']] = {"nama": p['nama'], "harga": p['harga'], "qty": qty}
        if st.button("➕ Tambahkan ke Keranjang"):
            st.session_state.cart = []
            for pid, data in items_input.items():
                if data["qty"] > 0:
                    st.session_state.cart.append(data)
            st.success("Keranjang diperbarui!")
            st.rerun()

        if st.session_state.cart:
            st.subheader("🛒 Keranjang")
            total = sum(item["harga"] * item["qty"] for item in st.session_state.cart)
            for item in st.session_state.cart:
                st.write(f"- {item['nama']} x{item['qty']} = Rp{item['harga']*item['qty']:,}")
            st.markdown(f"### Subtotal: **Rp{total:,}**")
            
            # Input tax
            tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=st.session_state.tax_rate, key="tax_input")
            tax_amount = total * tax_rate / 100
            grand_total = total + tax_amount
            st.write(f"Tax: Rp{int(tax_amount):,}")
            st.markdown(f"## Total Bayar: **Rp{int(grand_total):,}**")
            
            metode = st.radio("Metode Pembayaran", ["QRIS", "DuitNow QR", "GoPay", "Kartu Kredit", "Cash"])
            
            if st.button("✅ Selesaikan Pembayaran", type="primary", use_container_width=True):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trans_id = insert_transaction(
                    timestamp, total, tax_amount, int(grand_total), metode, "Sukses",
                    st.session_state.cart,
                    keterangan=f"Tax {tax_rate}%"
                )
                if trans_id:
                    st.session_state.last_transaction = {
                        'timestamp': timestamp,
                        'total': total,
                        'tax': tax_amount,
                        'tax_rate': tax_rate,
                        'grand_total': int(grand_total),
                        'metode': metode,
                        'status': 'Sukses',
                        'items': st.session_state.cart.copy()
                    }
                    st.session_state.cart = []
                    st.session_state.show_struk = True
                    st.rerun()
        else:
            st.info("Keranjang kosong, silakan pilih produk.")

# ====================== TAB DASHBOARD ======================
with tab2:
    st.header("📊 Dashboard Penjualan")
    df_trans = get_all_transactions()
    if df_trans.empty:
        st.info("Belum ada transaksi.")
    else:
        total_omset = df_trans["grand_total"].sum()
        st.metric("💰 Total Omset", f"Rp{total_omset:,.0f}")
        
        # Produk terlaris
        st.subheader("🏆 Produk Terlaris")
        all_items = []
        for tid in df_trans["id"]:
            items = get_transaction_items(tid)
            if not items.empty:
                all_items.append(items)
        if all_items:
            df_items = pd.concat(all_items)
            df_produk = df_items.groupby("nama")["qty"].sum().reset_index().sort_values("qty", ascending=False)
            fig_bar = px.bar(df_produk, x="nama", y="qty", color="nama", title="Produk Terlaris")
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Proporsi pembayaran
        st.subheader("📌 Proporsi Metode Pembayaran")
        metode_counts = df_trans["metode"].value_counts().reset_index()
        metode_counts.columns = ["Metode", "Jumlah"]
        fig_pie = px.pie(metode_counts, values="Jumlah", names="Metode", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # Riwayat transaksi
        with st.expander("📋 Riwayat Transaksi"):
            st.dataframe(df_trans.drop(columns=["id"], errors="ignore"), use_container_width=True)
            tid_pilih = st.selectbox("Detail item transaksi ID:", df_trans["id"].tolist())
            if tid_pilih:
                detail = get_transaction_items(tid_pilih)
                st.dataframe(detail[["nama", "harga", "qty"]], use_container_width=True)

# ====================== TAB KELOLA MENU ======================
with tab3:
    st.header("📋 Kelola Menu Makanan/Minuman")
    
    # Form tambah
    with st.form("add_menu"):
        st.subheader("Tambah Menu Baru")
        nama_baru = st.text_input("Nama")
        harga_baru = st.number_input("Harga", min_value=100, step=100)
        if st.form_submit_button("➕ Tambahkan"):
            if nama_baru:
                if add_menu_item(nama_baru, harga_baru):
                    st.success(f"{nama_baru} ditambahkan!")
                    st.rerun()
                else:
                    st.error("Nama sudah ada!")
            else:
                st.error("Nama tidak boleh kosong.")
    
    # Daftar menu
    st.subheader("Daftar Menu Saat Ini")
    menu = get_menu()
    if not menu.empty:
        for idx, row in menu.iterrows():
            col1, col2, col3, col4 = st.columns([3,2,1,1])
            col1.write(row["nama"])
            col2.write(f"Rp{row['harga']:,}")
            if col3.button("✏️", key=f"edit_{row['id']}"):
                st.session_state.edit_menu_id = row['id']
            if col4.button("🗑️", key=f"del_{row['id']}"):
                delete_menu_item(row['id'])
                st.rerun()
        
        # Form edit jika ada yang diklik
        if "edit_menu_id" in st.session_state and st.session_state.edit_menu_id:
            edit_id = st.session_state.edit_menu_id
            row = menu[menu['id'] == edit_id].iloc[0]
            with st.form("edit_menu_form"):
                st.subheader(f"Edit: {row['nama']}")
                nama_edit = st.text_input("Nama Baru", value=row['nama'])
                harga_edit = st.number_input("Harga Baru", value=row['harga'], step=100)
                if st.form_submit_button("💾 Simpan Perubahan"):
                    update_menu_item(edit_id, nama_edit, harga_edit)
                    st.session_state.edit_menu_id = None
                    st.success("Menu diperbarui!")
                    st.rerun()
