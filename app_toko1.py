import os
import sys
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import desc

# ===============================================
# 1. SETUP KONFIGURASI APLIKASI
# ===============================================

toko_app = Flask(__name__)

# Konfigurasi dari file yang diupload
toko_app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kunci_rahasia_dan_aman_sekali_toko_balokeren')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///shop.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
toko_app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

toko_app.config['UPLOAD_FOLDER'] = os.path.join(toko_app.root_path, 'static/product_images')
toko_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Pastikan folder upload ada
if not os.path.exists(toko_app.config['UPLOAD_FOLDER']):
    os.makedirs(toko_app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(toko_app)
login_manager = LoginManager(toko_app)
login_manager.login_view = 'login' 

# --- KONFIGURASI ADMIN OTOMATIS (GUNAKAN HASH PASSWORD ANDA) ---
# GANTI INI dengan HASH password yang sudah Anda buat!
ADMIN_DEFAULT_PASSWORD_HASH = generate_password_hash('admin12345') # Ganti dengan password yang Anda inginkan
ADMIN_DEFAULT_EMAIL = 'admin@toko.com' 

# ===============================================
# 2. MODEL DATABASE
# ===============================================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True) 
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='customer', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    items_json = db.Column(db.Text, nullable=False) # Menyimpan detail item dalam format JSON
    total_amount = db.Column(db.Integer, nullable=False)
    total_unique_amount = db.Column(db.Integer, nullable=True) # Total harga unik untuk verifikasi
    payment_method = db.Column(db.String(50), default='QRIS')
    payment_status = db.Column(db.String(50), default='Menunggu Pembayaran')
    user_keterangan = db.Column(db.Text, nullable=True) # Catatan pesanan keseluruhan

# ===============================================
# 3. HELPER DAN CONTEXT PROCESSOR (PERBAIKAN FINAL)
# ===============================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_user_admin():
    return current_user.is_authenticated and current_user.is_admin

# Helper untuk menghitung item di keranjang (PERBAIKAN: Menggunakan .values() dan default {})
@toko_app.context_processor
def cart_item_count_processor():
    session_cart = session.get('cart', {})
    
    # Memastikan cart adalah dictionary
    if not isinstance(session_cart, dict):
        return dict(cart_item_count=0)
    
    # Iterasi menggunakan .values() untuk menjumlahkan kuantitas
    count = sum(item_data.get('quantity', 0) for item_data in session_cart.values())
    
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
        phone = request.form.get('phone_number')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Password tidak cocok.', 'error')
            return redirect(url_for('signup'))

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email sudah terdaftar.', 'error')
            return redirect(url_for('signup'))

        new_user = User(email=email, phone_number=phone)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Akun berhasil dibuat! Silakan masuk.', 'success')
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
        
        if user and user.check_password(password):
            login_user(user, remember=True) # Tambahkan remember=True
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email atau Password salah.', 'error')

    return render_template('login.html')

# --- RUTE: LOGOUT ---
@toko_app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar.', 'info')
    return redirect(url_for('index'))

# --- RUTE: INDEX (HOME) ---
@toko_app.route('/')
@toko_app.route('/index')
def index():
    products = Product.query.order_by(desc(Product.id)).all()
    return render_template('index.html', products=products)

# --- RUTE: TAMBAH PRODUK (ADMIN) ---
@toko_app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not is_user_admin():
        flash('Akses Ditolak: Hanya Admin yang boleh menambahkan produk.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = int(request.form.get('price'))
        stock = int(request.form.get('stock'))
        uploaded_file = request.files.get('image_file')
        
        filename = 'default.jpg'
        if uploaded_file and uploaded_file.filename != '':
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(toko_app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)

        new_product = Product(
            name=name,
            description=description,
            price=price,
            stock=stock,
            image_file=filename
        )
        db.session.add(new_product)
        db.session.commit()
        
        flash(f'Produk "{name}" berhasil ditambahkan!', 'success')
        return redirect(url_for('index'))

    return render_template('add_product.html')

# --- RUTE: TAMBAH KE KERANJANG (PERBAIKAN: Menggunakan DICT) ---
@toko_app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))

    # Inisialisasi keranjang sebagai DICTIONARY jika belum ada/salah tipe
    if 'cart' not in session or not isinstance(session['cart'], dict):
        session['cart'] = {}
        
    product_id_str = str(product_id)
    
    # Tambahkan atau update item
    if product_id_str in session['cart']:
        session['cart'][product_id_str]['quantity'] += quantity
    else:
        # Tambah item baru dengan inisialisasi keterangan kosong
        session['cart'][product_id_str] = {
            'quantity': quantity,
            'keterangan': '' 
        }
        
    session.modified = True
    flash(f'{quantity}x {product.name} telah ditambahkan ke keranjang.', 'success')
    return redirect(url_for('index'))

# --- RUTE: HAPUS DARI KERANJANG ---
@toko_app.route('/remove_from_cart/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    product_id_str = str(product_id)
    if 'cart' in session and product_id_str in session['cart']:
        name = Product.query.get(product_id).name if Product.query.get(product_id) else 'Item'
        session['cart'].pop(product_id_str, None)
        session.modified = True
        flash(f'{name} telah dihapus dari keranjang.', 'info')
    return redirect(url_for('cart'))

# --- RUTE: UPDATE KUANTITAS ---
@toko_app.route('/update_quantity/<int:product_id>', methods=['POST'])
@login_required
def update_quantity(product_id):
    product_id_str = str(product_id)
    new_quantity = int(request.form.get('quantity', 1))

    if 'cart' in session and product_id_str in session['cart']:
        if new_quantity > 0:
            session['cart'][product_id_str]['quantity'] = new_quantity
            flash('Kuantitas berhasil diperbarui.', 'success')
        else:
            # Jika kuantitas 0, hapus item (opsional, sudah ada tombol hapus)
            session['cart'].pop(product_id_str, None)
            flash('Item dihapus dari keranjang.', 'info')
            
        session.modified = True
    return redirect(url_for('cart'))

# --- RUTE: UPDATE KETERANGAN ITEM & ORDER (PERBAIKAN: Rute Baru) ---
@toko_app.route('/update_notes', methods=['POST'])
@login_required
def update_notes():
    # Logika untuk menyimpan catatan pesanan keseluruhan
    order_keterangan = request.form.get('order_keterangan', '').strip()
    session['order_keterangan'] = order_keterangan
    
    # Logika untuk menyimpan keterangan per item
    if 'cart' in session and isinstance(session['cart'], dict):
        for key in session['cart'].keys():
            item_keterangan = request.form.get(f'keterangan_{key}', '').strip()
            session['cart'][key]['keterangan'] = item_keterangan
    
    session.modified = True
    flash('Catatan Keranjang berhasil diperbarui.', 'success')
    return redirect(url_for('cart'))


# --- RUTE: KERANJANG (PERBAIKAN: Menangani list lama) ---
@toko_app.route('/cart')
@login_required
def cart():
    session_cart = session.get('cart', {}) 
    
    # PERBAIKAN KRUSIAL: Jika sesi lama masih berupa LIST, kita harus meresetnya.
    if isinstance(session_cart, list):
        session.pop('cart', None)
        session.modified = True
        flash('Data keranjang lama telah direset. Silakan tambahkan item baru.', 'warning')
        return redirect(url_for('index'))
    
    cart_items = []
    total_price = 0
    
    for product_id_str, item_data in session_cart.items(): 
        # Ambil product dari database, pastikan ID-nya dikonversi ke integer
        product = Product.query.get(int(product_id_str))
        
        if product:
            quantity = item_data.get('quantity', 1)
            item_for_display = {
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'keterangan': item_data.get('keterangan', ''), 
            }
            cart_items.append(item_for_display)
            total_price += product.price * quantity
        
    order_keterangan = session.get('order_keterangan', '')

    return render_template('cart.html',
        cart_items=cart_items,
        total_price=total_price,
        order_keterangan=order_keterangan 
    )

# --- RUTE: CHECKOUT (PERBAIKAN: Menyimpan Keterangan) ---
@toko_app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    session_cart = session.get('cart', {})
    
    if not session_cart or not isinstance(session_cart, dict):
        flash('Keranjang belanja Anda kosong!', 'error')
        return redirect(url_for('index'))

    total_amount = 0
    items_json = []

    # Dapatkan 3 digit acak untuk total unik
    import random
    unique_suffix = random.randint(100, 999)

    for product_id_str, item_data in session_cart.items():
        product = Product.query.get(int(product_id_str))
        quantity = item_data.get('quantity', 1)
        
        if product and quantity > 0:
            subtotal = product.price * quantity
            total_amount += subtotal
            
            # Persiapan data untuk JSON (termasuk keterangan)
            items_json.append({
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'keterangan': item_data.get('keterangan', ''), # <--- Keterangan per item
            })
        else:
            # Hapus item yang tidak valid (jika produk tidak ada atau kuantitas 0)
            session_cart.pop(product_id_str, None)

    if not items_json:
        session.pop('cart', None)
        flash('Keranjang belanja Anda kosong setelah validasi produk.', 'error')
        session.modified = True
        return redirect(url_for('index'))

    # Hitung total unik
    final_unique_amount = total_amount + unique_suffix
    
    # Ambil catatan pesanan keseluruhan dari sesi
    order_keterangan = session.get('order_keterangan', '')
    
    new_order = Order(
        user_id=current_user.id,
        items_json=json.dumps(items_json),
        total_amount=total_amount,
        total_unique_amount=final_unique_amount,
        payment_method='QRIS',
        payment_status='Menunggu Pembayaran',
        user_keterangan=order_keterangan # <--- Catatan keseluruhan
    )
    
    db.session.add(new_order)
    db.session.commit()
    
    # Hapus keranjang dan keterangan dari sesi setelah checkout berhasil
    session.pop('cart', None)
    session.pop('order_keterangan', None)
    session.modified = True
    
    flash(f'Pesanan Anda (No. #{new_order.id}) telah dibuat! Total Bayar Unik: Rp {final_unique_amount:,.0f}.', 'success')
    return redirect(url_for('my_orders'))


# --- RUTE: DAFTAR PESANAN SAYA ---
@toko_app.route('/my_orders')
@login_required
def my_orders():
    # Ambil pesanan user yang sedang login, diurutkan dari yang terbaru
    orders = Order.query.filter_by(user_id=current_user.id).order_by(desc(Order.order_date)).all()
    
    parsed_orders = []
    for order in orders:
        items = json.loads(order.items_json) # Pastikan items_json diparse
        
        parsed_orders.append({
            'id': order.id,
            'order_date': order.order_date,
            'total_amount': order.total_amount,
            'total_unique_amount': order.total_unique_amount,
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status,
            'user_keterangan': order.user_keterangan # <--- Pastikan ini ada
        })

    return render_template('my_orders.html', orders=parsed_orders)

# --- RUTE: DASHBOARD ADMIN ---
@toko_app.route('/admin/orders')
@login_required
def admin_orders():
    if not is_user_admin():
        flash('Akses Ditolak: Hanya Admin yang dapat melihat dashboard.', 'error')
        return redirect(url_for('index'))
    
    # Ambil semua pesanan, diurutkan dari yang terbaru
    orders = Order.query.order_by(desc(Order.order_date)).all()
    
    parsed_orders = []
    for order in orders:
        items = json.loads(order.items_json)
        
        # Ambil data customer untuk tampilan admin
        customer = User.query.get(order.user_id)
        customer_name = customer.email if customer else 'Unknown User'
        phone_number = customer.phone_number if customer and customer.phone_number else '-'
        
        parsed_orders.append({
            'id': order.id,
            'user_id': order.user_id,
            'order_date': order.order_date,
            'customer_name': customer_name,
            'phone_number': phone_number,
            'user_keterangan': order.user_keterangan, # <--- Catatan keseluruhan
            'total_amount': order.total_amount,
            'total_unique_amount': order.total_unique_amount,
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status
        })

    return render_template('admin_orders.html', orders=parsed_orders)

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

# ===============================================
# 5. INISIASI DATABASE (PERBAIKAN FINAL)
# ===============================================

def init_db():
    # Fungsi ini HANYA boleh berisi operasi DB, dijalankan dalam app_context
    with toko_app.app_context():
        db.create_all() 
        
        # Inisiasi Admin Default
        admin_user = User.query.filter_by(email=ADMIN_DEFAULT_EMAIL).first()
        if not admin_user:
            admin_user = User(email=ADMIN_DEFAULT_EMAIL, is_admin=True, phone_number='08123456789')
            admin_user.password_hash = ADMIN_DEFAULT_PASSWORD_HASH
            db.session.add(admin_user)
            db.session.commit()
            print("Admin default berhasil diinisiasi!")
        
        # Inisiasi Produk Contoh
        if Product.query.count() == 0:
            products_data = [
                {'name': 'Baju Kaos Premium', 'description': 'Kaos cotton combed 30s, nyaman dipakai.', 'price': 150000, 'stock': 50, 'image_file': 'kaos.jpg'},
                {'name': 'Celana Jeans Slim Fit', 'description': 'Bahan denim terbaik, jahitan rapi.', 'price': 350000, 'stock': 30, 'image_file': 'jeans.jpg'},
                {'name': 'Hoodie Oversized', 'description': 'Hoodie tebal dan hangat, cocok untuk cuaca dingin.', 'price': 280000, 'stock': 20, 'image_file': 'hoodie.jpg'},
            ]
            for data in products_data:
                db.session.add(Product(**data))
            db.session.commit()
            print("Produk contoh berhasil ditambahkan.")
            
        print("Inisiasi DB Selesai.")

# ===============================================
# 6. EKSEKUSI APLIKASI
# ===============================================

if __name__ == '__main__':
    # Memastikan database diinisiasi saat file dijalankan
    init_db() 
    
    # Deteksi Sistem Operasi untuk memilih server WSGI
    if sys.platform == 'win32':
        # Jika di Windows, gunakan Waitress (perlu 'pip install waitress')
        try:
            from waitress import serve
            print("Menggunakan Waitress (Windows)...")
            serve(toko_app, host='0.0.0.0', port=5000)
        except ImportError:
            print("Peringatan: Waitress tidak terinstal. Gunakan server pengembangan Flask.")
            toko_app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    else:
        # Untuk Linux/macOS, jalankan server pengembangan Flask
        toko_app.run(debug=True, host='0.0.0.0', port=5000)