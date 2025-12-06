import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import make_response 
import csv 
from io import StringIO

# ===============================================
# 1. SETUP KONFIGURASI APLIKASI
# ===============================================

# Ganti nama aplikasi dari 'app' ke 'toko_app' untuk menghindari kebingungan
toko_app = Flask(__name__)
toko_app.config['SECRET_KEY'] = 'kunci_rahasia_dan_aman_sekali_toko_balokeren'

# 🚀 MODIFIKASI UNTUK DEPLOYMENT LIVE
# Ambil DATABASE_URL dari variabel lingkungan (untuk Render/PostgreSQL)
# Jika tidak ada, gunakan SQLite lokal sebagai fallback
database_url = os.environ.get('DATABASE_URL', 'sqlite:///shop.db')

# Khusus untuk Render/Heroku dengan PostgreSQL (psycopg2)
# Ini penting untuk mengganti skema 'postgres://' (lama) menjadi 'postgresql://' (standar SQLAlchemy)
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
    
toko_app.config['SQLALCHEMY_DATABASE_URI'] = database_url # <<< PERUBAHAN UTAMA
# ----------------------------------------

toko_app.config['UPLOAD_FOLDER'] = os.path.join(toko_app.root_path, 'static/product_images') 
toko_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(toko_app)
login_manager = LoginManager(toko_app)
login_manager.login_view = 'login' 

# --- KONFIGURASI ADMIN OTOMATIS (GUNAKAN HASH PASSWORD ANDA) ---
ADMIN_DEFAULT_PASSWORD_HASH = 'scrypt:32768:8:1$PIyIl6lXzMaTtKwV$d4a3b915cfcb231bc9b21d36b328a43374bb3880c7237b03f5787ff11630e1120aac5892da8819531add9dcbbf556fa67d762a547915bf111b6628d9e0a3d9c1' 
ADMIN_DEFAULT_EMAIL = 'admin@toko.com' 

# ===============================================
# 2. MODEL DATABASE
# ===============================================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True) 
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    image_file = db.Column(db.String(100), nullable=True, default='default.jpg')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Integer, nullable=False)
    items_json = db.Column(db.Text, nullable=False) # Menyimpan list item dalam format JSON
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(50), default='Menunggu Pembayaran')
    proof_image = db.Column(db.String(255), nullable=True) # Nama file bukti pembayaran
    order_date = db.Column(db.DateTime, default=datetime.utcnow)

# ===============================================
# 3. FUNGSI UTAMA DAN INIASI
# ===============================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_user_admin():
    return current_user.is_authenticated and current_user.is_admin

def init_db():
    # Gunakan pengecekan yang lebih universal atau pindahkan ke dalam app_context
    with toko_app.app_context():
        # db.drop_all() # Hati-hati menggunakan ini di live!
        db.create_all() # Ini akan membuat tabel jika belum ada

        print("Database dibuat, menambahkan Admin dan Produk awal (jika kosong)...")

        # --- LOGIKA OTOMATISASI ADMIN ---
        if User.query.filter_by(email=ADMIN_DEFAULT_EMAIL).first() is None:
            print(f"Menambahkan Admin Default: {ADMIN_DEFAULT_EMAIL}")
            admin_user = User(
                email=ADMIN_DEFAULT_EMAIL,
                password_hash=ADMIN_DEFAULT_PASSWORD_HASH,
                is_admin=True,
                phone_number='08123456789' 
            )
            db.session.add(admin_user)
        
        # --- LOGIKA PRODUK AWAL ---
        if Product.query.count() == 0:
            products_data = [
                {'name': 'Baju Kaos Premium', 'price': 150000, 'stock': 10, 'description': 'Bahan katun 30s, nyaman dipakai.'},
                {'name': 'Celana Jeans Slim Fit', 'price': 250000, 'stock': 5, 'description': 'Model terbaru, warna Dark Blue.'},
                {'name': 'Sepatu Sneakers Pria', 'price': 300000, 'stock': 7, 'description': 'Sporty dan stylish.'}
            ]
            for data in products_data:
                # Tambahkan 'image_file' secara default agar tidak error
                data['image_file'] = f"{data['name'].lower().replace(' ', '_')}.jpg"
                db.session.add(Product(**data))

        db.session.commit()
        print("Inisiasi DB Selesai.")

# Helper untuk menghitung item di keranjang
@toko_app.context_processor
def cart_item_count_processor():
    count = sum(item['quantity'] for item in session.get('cart', []))
    return dict(cart_item_count=count)

# ===============================================
# 4. RUTE & LOGIKA APLIKASI
# ===============================================

# --- RUTE: REGISTRASI (SIGN UP) ---
@toko_app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone') 
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        
        if user:
            flash('Email ini sudah terdaftar. Silakan login.', 'error')
            return redirect(url_for('signup'))

        new_user = User(
            email=email, 
            phone_number=phone, 
            is_admin=False
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Akun berhasil dibuat! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')


# --- RUTE: LOGIN ---
@toko_app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash('Login gagal. Periksa Email dan Password Anda.', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash('Berhasil login!', 'success')
        return redirect(url_for('index'))
    return render_template('login.html')

# --- RUTE: LOGOUT ---
@toko_app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- RUTE: HALAMAN UTAMA (INDEX/TOKO) ---
@toko_app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

# --- RUTE: TAMBAH PRODUK BARU ---
@toko_app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not is_user_admin():
        return "Akses Ditolak: Hanya Admin yang dapat menambahkan produk.", 403

    if request.method == 'POST':
        name = request.form.get('name')
        price = int(request.form.get('price'))
        stock = int(request.form.get('stock'))
        description = request.form.get('description')
        
        # --- LOGIKA UNGGAH FILE BARU ---
        uploaded_file = request.files.get('image')
        image_filename = 'default.jpg' # Default jika tidak ada file
        
        if uploaded_file and uploaded_file.filename != '':
            # Amankan nama file dan simpan di folder UPLOAD_FOLDER
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(toko_app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)
            image_filename = filename
        # -------------------------------
        
        new_product = Product(
            name=name, 
            price=price, 
            stock=stock, 
            description=description,
            image_file=image_filename # <--- SIMPAN NAMA FILE
        )
        db.session.add(new_product)
        db.session.commit()
        
        flash(f'Produk "{name}" berhasil ditambahkan!', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_product.html')

# --- RUTE: EDIT PRODUK (ADMIN) ---
@toko_app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not is_user_admin():
        return "Akses Ditolak: Hanya Admin yang dapat mengedit produk.", 403

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form.get('name')
        product.price = int(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        product.description = request.form.get('description')

        # --- LOGIKA UNGGAH FILE (JIKA ADA PERUBAHAN GAMBAR) ---
        uploaded_file = request.files.get('image')
        if uploaded_file and uploaded_file.filename != '':
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(toko_app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)
            product.image_file = filename
        # ---------------------------------------------------
        
        db.session.commit()
        flash(f'Produk "{product.name}" berhasil diperbarui!', 'success')
        return redirect(url_for('index')) 

    return render_template('edit_product.html', product=product)

# --- RUTE: HAPUS PRODUK (ADMIN) ---
@toko_app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if not is_user_admin():
        return "Akses Ditolak: Hanya Admin yang dapat menghapus produk.", 403

    product = Product.query.get_or_404(product_id)
    
    # Opsional: Hapus file gambar dari server
    if product.image_file != 'default.jpg':
        file_path = os.path.join(toko_app.config['UPLOAD_FOLDER'], product.image_file)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(product)
    db.session.commit()
    flash(f'Produk "{product.name}" berhasil dihapus.', 'success')
    return redirect(url_for('index'))

# --- RUTE: TAMBAH KE KERANJANG ---
@toko_app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = 1 

    if 'cart' not in session:
        session['cart'] = []

    cart_items = session['cart']
    item_found = False
    
    for item in cart_items:
        if item['id'] == product_id:
            item['quantity'] += quantity
            item_found = True
            break
            
    if not item_found:
        cart_items.append({
            'id': product_id,
            'name': product.name,
            'price': product.price,
            'quantity': quantity
        })

    session['cart'] = cart_items
    session.modified = True 
    flash(f'{product.name} berhasil ditambahkan ke keranjang!', 'success')
    return redirect(url_for('index'))


# --- RUTE: UPDATE KUANTITAS KERANJANG ---
@toko_app.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart_quantity(product_id):
    action = request.form.get('action') 
    cart_items = session.get('cart', [])
    updated_cart = []
    
    for item in cart_items:
        if item['id'] == product_id:
            if action == 'increase':
                item['quantity'] += 1
                updated_cart.append(item)
            elif action == 'decrease':
                item['quantity'] -= 1
                
                if item['quantity'] > 0:
                    updated_cart.append(item)
        else:
            updated_cart.append(item)
            
    session['cart'] = updated_cart
    session.modified = True
    
    return redirect(url_for('cart'))

# --- RUTE: HAPUS ITEM DARI KERANJANG ---
@toko_app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] if item['id'] != product_id]
        session.modified = True
        flash('Item berhasil dihapus dari keranjang.', 'success')
    return redirect(url_for('cart'))


# --- RUTE: TAMPILAN KERANJANG ---
@toko_app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total_price = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)


# --- RUTE: CHECKOUT ---
@toko_app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('Keranjang belanja Anda kosong!', 'error')
        return redirect(url_for('index'))
    
    total_price = sum(item['price'] * item['quantity'] for item in cart_items)

    if request.method == 'POST':
        payment_method = request.form.get('payment_method')

        # 1. Simpan pesanan awal ke database untuk mendapatkan ID Pesanan
        items_json = json.dumps(cart_items)
        new_order = Order(
            customer_name=current_user.email,
            total_amount=total_price,
            items_json=items_json,
            payment_method=payment_method,
            payment_status='Menunggu Pembayaran'
        )
        db.session.add(new_order)
        db.session.commit() 

        # --- LOGIKA KODE PEMBAYARAN UNIK & UPDATE STOK OTOMATIS ---
        
        payment_suffix = new_order.id % 1000 
        payment_suffix_str = f"{payment_suffix:03d}"
        final_amount_to_pay = total_price + payment_suffix
        
        # --- Update Stok Otomatis ---
        try:
            for item in cart_items:
                product = Product.query.get(item['id'])
                if product and product.stock >= item['quantity']:
                    product.stock -= item['quantity']
                else:
                    db.session.rollback()
                    flash(f'Gagal checkout: Stok {product.name} tidak mencukupi atau produk tidak ditemukan.', 'error')
                    return redirect(url_for('cart'))
            
            db.session.commit() 
        
        except Exception as e:
            db.session.rollback()
            flash('Terjadi kesalahan saat memproses stok. Pesanan dibatalkan.', 'error')
            print(f"Checkout Error: {e}")
            return redirect(url_for('cart'))


        # --- Finalisasi Transaksi ---
        today = datetime.now()
        order_code = today.strftime(f"TKO%y%m%d-{new_order.id}")
        
        session.pop('last_order_code', None)
        session.pop('last_final_amount', None)
        session.pop('last_payment_suffix', None)
        
        session['payment_info'] = { 
            'code': order_code,
            'amount': final_amount_to_pay,
            'suffix': payment_suffix_str,
            'method': payment_method
        }

        # Kosongkan Keranjang
        session.pop('cart', None)
        session.modified = True
        
        flash(f'Pesanan Anda (Kode Transaksi: #{order_code}) berhasil dibuat!', 'success')
        
        return redirect(url_for('my_orders'))
        
    return render_template('checkout.html', cart_items=cart_items, total_price=total_price)


# --- RUTE: PESANAN SAYA (USER) ---
@toko_app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(customer_name=current_user.email).order_by(Order.order_date.desc()).all()
    
    payment_info = session.pop('payment_info', None)
    session.modified = True 

    parsed_orders = []
    for order in orders:
        
        safe_total_amount = order.total_amount if order.total_amount is not None else 0
        
        payment_suffix = order.id % 1000
        final_unique_amount = safe_total_amount + payment_suffix 
        items = json.loads(order.items_json)
        
        order_code = order.order_date.strftime(f"TKO%y%m%d-{order.id}") 
        
        parsed_orders.append({
            'id': order.id,
            'order_code': order_code, 
            'order_date': order.order_date, 
            'total_amount': safe_total_amount, 
            'total_unique_amount': final_unique_amount,
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status
        })

    return render_template('my_orders.html', orders=parsed_orders, payment_info=payment_info)


# --- RUTE: ADMIN DASHBOARD (MENGELOLA PESANAN) ---
@toko_app.route('/admin/orders')
@login_required
def admin_orders():
    if not is_user_admin():
        return "Akses Ditolak: Anda bukan Admin.", 403

    orders = Order.query.order_by(Order.order_date.desc()).all()

    parsed_orders = []
    for order in orders:
        # --- 1. Ambil Data Customer (Enrichment) ---
        customer = User.query.filter_by(email=order.customer_name).first()
        phone_number = customer.phone_number if customer else 'N/A'
        
        safe_total_amount = order.total_amount if order.total_amount is not None else 0

        # --- 2. Hitung Total Unik ---
        payment_suffix = order.id % 1000 
        final_unique_amount = safe_total_amount + payment_suffix 

        # --- TAMBAHAN: Buat Order Code ---
        order_code = order.order_date.strftime(f"TKO%y%m%d-{order.id}") 

        # --- 3. Parse Items ---
        items = json.loads(order.items_json)
        
        parsed_orders.append({
            'id': order.id,
            'order_code': order_code, 
            'order_date': order.order_date,
            'customer_name': order.customer_name,
            'phone_number': phone_number,  
            'total_amount': safe_total_amount, 
            'total_unique_amount': final_unique_amount, 
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status
        })

    return render_template('admin_orders.html', orders=parsed_orders)
# app_toko.py (Tambahkan di bagian rute Admin)

# --- RUTE: DAFTAR USER (ADMIN) ---
@toko_app.route('/admin/users')
@login_required
def admin_users():
    # Pengecekan Wajib: Pastikan hanya Admin yang bisa akses
    if not is_user_admin():
        flash('Akses Ditolak: Hanya Admin yang dapat melihat daftar user.', 'danger')
        return redirect(url_for('index'))
    
    # Hitung total user
    total_users = User.query.count()
    
    # Ambil semua user, diurutkan, dan filter Admin yang sedang login agar tidak tampil dua kali
    # (Opsional: Anda bisa hapus filter jika ingin melihat semua user termasuk diri sendiri)
    users = User.query.filter(User.id != current_user.id).order_by(User.id.desc()).all()
    
    return render_template('admin_users.html', total_users=total_users, users=users)

# --- RUTE BARU: EKSPOR DATA USER KE CSV ---
@toko_app.route('/admin/users/export', methods=['GET'])
@login_required
def export_users_csv():
    # 1. Pengecekan Wajib Admin
    if not is_user_admin():
        return "Akses Ditolak", 403

    # 2. Query Data User
    # Ambil semua user (termasuk admin)
    users = User.query.order_by(User.id.asc()).all()
    
    # 3. Buat objek StringIO untuk menampung data CSV
    si = StringIO()
    cw = csv.writer(si)

    # 4. Tulis Header (Nama Kolom)
    header = ['ID', 'Email', 'Nomor HP', 'Status Admin']
    cw.writerow(header)

    # 5. Tulis Baris Data
    for user in users:
        # Konversi status boolean is_admin menjadi 'Ya' atau 'Tidak'
        admin_status = 'Ya' if user.is_admin else 'Tidak'
        
        row = [
            user.id,
            user.email,
            user.phone_number if user.phone_number else '', # Isi kosong jika None
            admin_status
        ]
        cw.writerow(row)

    # 6. Buat Response File
    output = si.getvalue()
    response = make_response(output)
    
    # Tambahkan header agar browser mendownload sebagai file CSV
    response.headers["Content-Disposition"] = "attachment; filename=daftar_user_toko_baiko.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response

# --- RUTE: UPDATE KETERANGAN PER-ITEM KERANJANG ---
@toko_app.route('/update_item_keterangan/<int:product_id>', methods=['POST'])
@login_required
def update_item_keterangan(product_id):
    if 'cart' not in session or not session['cart']:
        flash('Keranjang kosong.', 'danger')
        return redirect(url_for('cart'))

    # Ambil data dari form
    new_keterangan = request.form.get('item_keterangan', '').strip()
    
    # Ambil index item unik dari form
    try:
        item_index = int(request.form.get('item_index'))
    except (ValueError, TypeError):
        flash('Data keranjang tidak valid.', 'danger')
        return redirect(url_for('cart'))

    cart_items = session['cart']
    
    # Cek apakah index valid dan cocok dengan product_id
    if 0 <= item_index < len(cart_items) and cart_items[item_index]['id'] == product_id:
        item = cart_items[item_index]
        
        # Update details
        item['keterangan'] = new_keterangan
        
        session['cart'] = cart_items
        session.modified = True
        flash(f'Keterangan untuk {item["name"]} berhasil diperbarui!', 'success')
    else:
        flash('Item keranjang tidak ditemukan atau data tidak valid.', 'danger')
        
    return redirect(url_for('cart'))
    
# --- RUTE: UPDATE STATUS PESANAN (ADMIN) ---
@toko_app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
@login_required
def update_order_status(order_id):
    if not is_user_admin():
        return "Akses Ditolak: Hanya Admin yang boleh mengubah status pesanan.", 403
    
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('new_status')
    
    if new_status:
        order.payment_status = new_status
        db.session.commit()
        flash(f'Status pesanan #{order_id} berhasil diupdate menjadi {new_status}', 'success')
    
    return redirect(url_for('admin_orders'))

# --- RUTE: HAPUS PESANAN (ADMIN) ---
@toko_app.route('/admin/delete_order/<int:order_id>', methods=['POST'])
@login_required
def delete_order(order_id):
    # 1. Pengecekan Admin
    if not is_user_admin():
        flash('Akses Ditolak: Hanya Admin yang boleh menghapus pesanan.', 'danger')
        return redirect(url_for('admin_orders'))
    
    # 2. Cari Pesanan
    order = Order.query.get(order_id)
    
    if order:
        # 3. Hapus Pesanan
        db.session.delete(order)
        db.session.commit()
        flash(f'Pesanan #{order_id} berhasil dihapus dari database.', 'success')
    else:
        flash(f'Pesanan dengan ID #{order_id} tidak ditemukan.', 'danger')
        
    return redirect(url_for('admin_orders'))

# ===============================================
# 5. EKSEKUSI APLIKASI
# ===============================================

# 💡 Catatan: Saat di-deploy menggunakan Gunicorn (sesuai Procfile), 
# init_db() tidak akan dipanggil melalui blok __name__ == '__main__'.
# Anda mungkin perlu menjalankan init_db() di luar blok ini atau 
# menggunakan Render 'Build Command' untuk menjalankan script inisiasi DB.

if __name__ == '__main__':
    # Memastikan database diinisiasi saat file dijalankan (hanya untuk pengembangan lokal)
    init_db() 
    
    # Jalankan aplikasi dengan nama baru 'toko_app'
    toko_app.run(debug=True)