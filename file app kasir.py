import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import hashlib
import os

# ------------------------------
# Database
# ------------------------------
DB_PATH = "/tmp/kasir.db"

def init_db():
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.close()
        except:
            os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS transactions")
    c.execute("DROP TABLE IF EXISTS transaction_items")

    c.execute('''
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total INTEGER NOT NULL,
            tax REAL NOT NULL DEFAULT 0,
            grand_total INTEGER NOT NULL,
            metode TEXT NOT NULL,
            status TEXT NOT NULL,
            keterangan TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            nama TEXT NOT NULL,
            harga INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT UNIQUE,
            harga INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

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

    defaults = {
        "pin_hash": hashlib.sha256("000000".encode()).hexdigest(),
        "recovery_code": "ADMIN123",
        "tax_rate": "10",
        "currency_symbol": "Rp"
    }
    for key, val in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

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

def verify_recovery_code(code):
    stored = get_setting("recovery_code")
    return stored == code

def get_currency():
    sym = get_setting("currency_symbol")
    return sym if sym else "Rp"

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
    tax_str = get_setting("tax_rate")
    st.session_state.tax_rate = float(tax_str) if tax_str else 10.0
if "currency_symbol" not in st.session_state:
    st.session_state.currency_symbol = get_currency()
if "show_struk" not in st.session_state:
    st.session_state.show_struk = False
if "last_transaction" not in st.session_state:
    st.session_state.last_transaction = None
if "show_reset" not in st.session_state:
    st.session_state.show_reset = False

# ------------------------------
# Halaman Login
# ------------------------------
if not st.session_state.logged_in:
    st.set_page_config(page_title="Login Kasir", page_icon="🔐")
    st.title("🔐 Akses Kasir")

    if st.session_state.show_reset:
        st.subheader("🔄 Reset PIN")
        st.info("Masukkan kode pemulihan untuk mereset PIN ke 000000.")
        recovery_input = st.text_input("Kode Pemulihan", type="password")
        if st.button("✅ Reset PIN"):
            if verify_recovery_code(recovery_input):
                change_pin("000000")
                st.success("PIN berhasil direset ke 000000. Silakan login.")
                st.session_state.show_reset = False
                st.rerun()
            else:
                st.error("Kode pemulihan salah!")
        if st.button("⬅️ Kembali ke Login"):
            st.session_state.show_reset = False
            st.rerun()
    else:
        with st.form("login_form"):
            pin = st.text_input("Masukkan PIN", type="password", max_chars=6)
            col1, col2 = st.columns(2)
            with col1:
                login_btn = st.form_submit_button("Masuk")
            with col2:
                reset_btn = st.form_submit_button("❓ Lupa PIN?")

            if login_btn:
                if verify_pin(pin):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("PIN salah!")
            if reset_btn:
                st.session_state.show_reset = True
                st.rerun()
    st.stop()

# ==============================
# SETELAH LOGIN
# ==============================
st.set_page_config(page_title="Kasir & Dashboard", layout="wide")
st.title("🧾 Kasir & Dashboard")

# Sidebar
with st.sidebar:
    st.write("✅ Login berhasil")
    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.cart = []
        st.rerun()
    st.markdown("---")
    st.subheader("⚙️ Pengaturan")

    # Tax rate
    new_tax = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, step=0.5,
                              value=st.session_state.tax_rate)
    if st.button("Simpan Tax Default"):
        st.session_state.tax_rate = new_tax
        update_setting("tax_rate", str(new_tax))
        st.success("Tax rate disimpan!")


    # Mata uang
    new_currency = st.text_input("Simbol Mata Uang", value=st.session_state.currency_symbol)
    if st.button("Simpan Mata Uang"):
        # Update session state langsung
        st.session_state.currency_symbol = new_currency
        # Simpan ke database
        update_setting("currency_symbol", new_currency)
        st.success(f"Mata uang berubah menjadi {new_currency}")
        # Tidak perlu st.rerun(), Streamlit akan otomatis refresh widget

    # Ganti PIN
    with st.expander("🔑 Ganti PIN"):
        old_pin = st.text_input("PIN Lama", type="password", key="old_pin")
        new_pin = st.text_input("PIN Baru", type="password", key="new_pin")
        if st.button("Simpan PIN Baru"):
            if verify_pin(old_pin):
                change_pin(new_pin)
                st.success("PIN berhasil diubah!")
            else:
                st.error("PIN lama salah!")

    # Ganti Kode Pemulihan
    with st.expander("🔄 Ganti Kode Pemulihan"):
        current_code = get_setting("recovery_code")
        st.text(f"Kode saat ini: {current_code}")
        new_code = st.text_input("Kode Baru", type="password", key="new_code")
        pin_confirm = st.text_input("PIN Konfirmasi", type="password", key="pin_confirm")
        if st.button("Simpan Kode Pemulihan"):
            if not verify_pin(pin_confirm):
                st.error("PIN konfirmasi salah!")
            elif len(new_code) < 6:
                st.error("Kode minimal 6 karakter.")
            else:
                update_setting("recovery_code", new_code)
                st.success("Kode pemulihan berhasil diubah!")

# Ambil data menu
menu_df = get_menu()
PRODUK = menu_df.to_dict('records')
CURR = st.session_state.currency_symbol

tab1, tab2, tab3 = st.tabs(["🛒 Kasir", "📊 Dashboard", "📋 Kelola Menu"])

# ====================== TAB KASIR ======================
with tab1:
    st.header("Transaksi Baru")

    if st.session_state.show_struk and st.session_state.last_transaction:
        trans = st.session_state.last_transaction
        items = trans['items']
        st.subheader("🧾 Struk Pembayaran")

        # Bangun HTML struk dengan CSS print
        items_html = ""
        for item in items:
            subtotal = item['harga'] * item['qty']
            items_html += f"<tr><td>{item['nama']} x{item['qty']}</td><td style='text-align:right;'>{CURR} {subtotal:,}</td></tr>"

        struk_html = f"""
        <html>
        <head>
        <style>
          @media print {{
            body * {{
              visibility: hidden;
            }}
            #printable, #printable * {{
              visibility: visible;
            }}
            #printable {{
              position: absolute;
              left: 0;
              top: 0;
              width: 100%;
              padding: 20px;
            }}
          }}
        </style>
        </head>
        <body>
          <div id="printable">
            <h3 style="text-align:center;">STRUK PEMBAYARAN</h3>
            <p style="text-align:center;">{trans['timestamp']}</p>
            <hr>
            <table style="width:100%;">
              {items_html}
            </table>
            <hr>
            <p>Subtotal: <b>{CURR} {trans['total']:,}</b></p>
            <p>Tax ({trans['tax_rate']:.1f}%): <b>{CURR} {int(trans['tax']):,}</b></p>
            <h3>Total: <b>{CURR} {trans['grand_total']:,}</b></h3>
            <p>Metode: <b>{trans['metode']}</b></p>
            <p>Status: <b>{trans['status']}</b></p>
          </div>
          <button onclick="window.print()" style="margin:20px; padding:10px 20px;">🖨️ Cetak Struk</button>
        </body>
        </html>
        """
        st.components.v1.html(struk_html, height=500, scrolling=True)

        if st.button("✅ Selesai", use_container_width=True):
            st.session_state.show_struk = False
            st.session_state.last_transaction = None
            st.rerun()
    else:
        st.subheader("Menu")
        items_input = {}
        cols = st.columns(3)
        for i, p in enumerate(PRODUK):
            with cols[i % 3]:
                qty = st.number_input(f"{p['nama']} ({CURR}{p['harga']:,})", 0, 20, 0, key=f"qty_{p['id']}")
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
                st.write(f"- {item['nama']} x{item['qty']} = {CURR}{item['harga']*item['qty']:,}")
            st.markdown(f"### Subtotal: **{CURR}{total:,}**")

            tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, step=0.5,
                                       value=st.session_state.tax_rate, key="tax_input")
            tax_amount = total * tax_rate / 100
            grand_total = total + tax_amount
            st.write(f"Tax: {CURR}{int(tax_amount):,}")
            st.markdown(f"## Total Bayar: **{CURR}{int(grand_total):,}**")

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
            st.info("Keranjang kosong.")

# ====================== TAB DASHBOARD ======================
with tab2:
    st.header("📊 Dashboard Penjualan")
    df_trans = get_all_transactions()
    if df_trans.empty:
        st.info("Belum ada transaksi.")
    else:
        total_omset = df_trans["grand_total"].sum()
        st.metric("💰 Total Omset", f"{CURR}{total_omset:,.0f}")

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

        st.subheader("📌 Proporsi Metode Pembayaran")
        metode_counts = df_trans["metode"].value_counts().reset_index()
        metode_counts.columns = ["Metode", "Jumlah"]
        fig_pie = px.pie(metode_counts, values="Jumlah", names="Metode", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

        with st.expander("📋 Riwayat Transaksi"):
            st.dataframe(df_trans.drop(columns=["id"], errors="ignore"), use_container_width=True)
            tid_pilih = st.selectbox("Detail item transaksi ID:", df_trans["id"].tolist())
            if tid_pilih:
                detail = get_transaction_items(tid_pilih)
                st.dataframe(detail[["nama", "harga", "qty"]], use_container_width=True)

# ====================== TAB KELOLA MENU ======================
with tab3:
    st.header("📋 Kelola Menu")
    with st.form("add_menu"):
        st.subheader("Tambah Menu Baru")
        nama_baru = st.text_input("Nama")
        harga_baru = st.number_input(f"Harga ({CURR})", min_value=100, step=100)
        if st.form_submit_button("➕ Tambahkan"):
            if nama_baru:
                if add_menu_item(nama_baru, harga_baru):
                    st.success(f"{nama_baru} ditambahkan!")
                    st.rerun()
                else:
                    st.error("Nama sudah ada!")
            else:
                st.error("Nama tidak boleh kosong.")

    st.subheader("Daftar Menu")
    menu = get_menu()
    if not menu.empty:
        for idx, row in menu.iterrows():
            col1, col2, col3, col4 = st.columns([3,2,1,1])
            col1.write(row["nama"])
            col2.write(f"{CURR}{row['harga']:,}")
            if col3.button("✏️", key=f"edit_{row['id']}"):
                st.session_state.edit_menu_id = row['id']
            if col4.button("🗑️", key=f"del_{row['id']}"):
                delete_menu_item(row['id'])
                st.rerun()

        if "edit_menu_id" in st.session_state and st.session_state.edit_menu_id:
            edit_id = st.session_state.edit_menu_id
            row = menu[menu['id'] == edit_id].iloc[0]
            with st.form("edit_menu_form"):
                st.subheader(f"Edit: {row['nama']}")
                nama_edit = st.text_input("Nama Baru", value=row['nama'])
                harga_edit = st.number_input(f"Harga Baru ({CURR})", value=row['harga'], step=100)
                if st.form_submit_button("💾 Simpan Perubahan"):
                    update_menu_item(edit_id, nama_edit, harga_edit)
                    st.session_state.edit_menu_id = None
                    st.success("Menu diperbarui!")
                    st.rerun()
