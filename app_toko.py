import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ===============================================
# 1. SETUP KONFIGURASI APLIKASI
# ===============================================

# Ganti nama aplikasi dari 'app' ke 'toko_app' untuk menghindari kebingungan
toko_app = Flask(__name__)
toko_app.config['SECRET_KEY'] = 'kunci_rahasia_dan_aman_sekali_toko_balokeren'
toko_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
toko_app.config['UPLOAD_FOLDER'] = os.path.join(toko_app.root_path, 'static/product_images') # <--- TAMBAH INI
toko_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(toko_app)
login_manager = LoginManager(toko_app)
login_manager.login_view = 'login' # Rute yang harus dikunjungi jika belum login

# --- KONFIGURASI ADMIN OTOMATIS (GUNAKAN HASH PASSWORD ANDA) ---
# GANTI INI dengan HASH password yang sudah Anda buat di langkah sebelumnya!
# Contoh: generate_password_hash('password_aman_anda')
ADMIN_DEFAULT_PASSWORD_HASH = 'scrypt:32768:8:1$PIyIl6lXzMaTtKwV$d4a3b915cfcb231bc9b21d36b328a43374bb3880c7237b03f5787ff11630e1120aac5892da8819531add9dcbbf556fa67d762a547915bf111b6628d9e0a3d9c1' 
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
    if not os.path.exists('shop.db'):
        with toko_app.app_context():
            db.create_all()
            print("Database dibuat, menambahkan Admin dan Produk awal...")

            # --- LOGIKA OTOMATISASI ADMIN ---
            if User.query.count() == 0:
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
    # Mengirim status is_admin ke template
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

# app_toko.py

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
            # Opsional: Hapus gambar lama jika tidak default
            # if product.image_file != 'default.jpg' and os.path.exists(os.path.join(toko_app.config['UPLOAD_FOLDER'], product.image_file)):
            #     os.remove(os.path.join(toko_app.config['UPLOAD_FOLDER'], product.image_file))
            product.image_file = filename
        # ---------------------------------------------------
        
        db.session.commit()
        flash(f'Produk "{product.name}" berhasil diperbarui!', 'success')
        return redirect(url_for('index')) # Kembali ke halaman utama atau daftar produk

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
    quantity = 1 # Kuantitas default saat ditambahkan

    # Inisialisasi keranjang jika belum ada
    if 'cart' not in session:
        session['cart'] = []

    cart_items = session['cart']
    item_found = False
    
    # Perbarui kuantitas jika produk sudah ada
    for item in cart_items:
        if item['id'] == product_id:
            item['quantity'] += quantity
            item_found = True
            break
            
    # Tambahkan produk baru jika belum ada
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
    action = request.form.get('action') # 'increase' atau 'decrease'
    cart_items = session.get('cart', [])
    updated_cart = []
    
    for item in cart_items:
        if item['id'] == product_id:
            if action == 'increase':
                item['quantity'] += 1
                updated_cart.append(item)
            elif action == 'decrease':
                item['quantity'] -= 1
                
                # Hanya simpan item jika kuantitas > 0
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


# app_toko.py

# ... (Pastikan Anda mengimpor datetime dari datetime) ...

# app_toko.py

# ...
# app_toko.py

# ... (pastikan import datetime dari datetime ada di bagian atas file) ...
from datetime import datetime
# ...

# app_toko.py

# ... (Pastikan Anda mengimpor datetime dari datetime) ...

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
        db.session.commit() # <<< COMMIT PERTAMA: Wajib dilakukan agar new_order.id terisi

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
            
            db.session.commit() # <<< COMMIT KEDUA: Simpan perubahan stok
        
        except Exception as e:
            db.session.rollback()
            flash('Terjadi kesalahan saat memproses stok. Pesanan dibatalkan.', 'error')
            print(f"Checkout Error: {e}")
            return redirect(url_for('cart'))


        # --- Finalisasi Transaksi ---
        today = datetime.now()
        order_code = today.strftime(f"TKO%y%m%d-{new_order.id}")
        
        # =========================================================
        # LANGKAH PERUBAHAN: SIMPAN DETAIL PEMBAYARAN KE SESSION
        # Menggunakan struktur kunci (code, amount, suffix) yang diharapkan my_orders.html
        # =========================================================
        session.pop('last_order_code', None)
        session.pop('last_final_amount', None)
        session.pop('last_payment_suffix', None)
        
        session['payment_info'] = { 
            'code': order_code,
            'amount': final_amount_to_pay,
            'suffix': payment_suffix_str,
            'method': payment_method
        }
        # =========================================================

        # Kosongkan Keranjang
        session.pop('cart', None)
        session.modified = True
        
        # Gunakan flash message yang lebih umum
        flash(f'Pesanan Anda (Kode Transaksi: #{order_code}) berhasil dibuat!', 'success')
        
        # Arahkan ke halaman pesanan saya
        return redirect(url_for('my_orders'))
        
    return render_template('checkout.html', cart_items=cart_items, total_price=total_price)


# app_toko.py

# app_toko.py

# app_toko.py

# --- RUTE: PESANAN SAYA (USER) ---
@toko_app.route('/my_orders')
@login_required
def my_orders():
    # 1. PERBAIKAN: Ganti Order.timestamp.desc() menjadi Order.order_date.desc()
    orders = Order.query.filter_by(customer_name=current_user.email).order_by(Order.order_date.desc()).all()
    
    payment_info = session.pop('payment_info', None) # Ambil instruksi pembayaran dari checkout
    session.modified = True # Penting setelah pop

    parsed_orders = []
    for order in orders:
        
        # Penanganan data lama yang mungkin NULL/None
        safe_total_amount = order.total_amount if order.total_amount is not None else 0
        
        payment_suffix = order.id % 1000
        final_unique_amount = safe_total_amount + payment_suffix # Menggunakan nilai yang aman
        items = json.loads(order.items_json)
        
        # --- TAMBAHAN: Buat Order Code ---
        order_code = order.order_date.strftime(f"TKO%y%m%d-{order.id}") # <<< BUAT KODE TRANSAKSI
        
        parsed_orders.append({
            'id': order.id,
            'order_code': order_code, # <<< KIRIM KODE TRANSAKSI
            # 2. PERBAIKAN: Ganti kunci 'timestamp' menjadi 'order_date'
            'order_date': order.order_date, 
            'total_amount': safe_total_amount, # Menggunakan nilai yang aman
            'total_unique_amount': final_unique_amount,
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status
        })

    return render_template('my_orders.html', orders=parsed_orders, payment_info=payment_info)


# app_toko.py (Ganti fungsi admin_orders lama)

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
        
        # Penanganan data lama yang mungkin NULL/None
        safe_total_amount = order.total_amount if order.total_amount is not None else 0

        # --- 2. Hitung Total Unik ---
        payment_suffix = order.id % 1000 
        final_unique_amount = safe_total_amount + payment_suffix # Menggunakan nilai yang aman

        # --- TAMBAHAN: Buat Order Code ---
        order_code = order.order_date.strftime(f"TKO%y%m%d-{order.id}") # <<< BUAT KODE TRANSAKSI

        # --- 3. Parse Items ---
        items = json.loads(order.items_json)
        
        parsed_orders.append({
            'id': order.id,
            'order_code': order_code, # <<< KIRIM KODE TRANSAKSI
            'order_date': order.order_date,
            'customer_name': order.customer_name,
            'phone_number': phone_number,  # Tambahan dari enrichment
            'total_amount': safe_total_amount, # Menggunakan nilai yang aman
            'total_unique_amount': final_unique_amount, # Total Unik
            'order_items': items,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status
        })

    # Catatan: Kita tidak lagi mengirim 'json=json' karena parsing sudah dilakukan di sini.
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
# 5. EKSEKUSI APLIKASI
# ===============================================

if __name__ == '__main__':
    # Memastikan database diinisiasi saat file dijalankan
    init_db() 
    
    # Jalankan aplikasi dengan nama baru 'toko_app'
    toko_app.run(debug=True)