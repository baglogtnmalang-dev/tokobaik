# init_db.py

# Import fungsi init_db dari aplikasi utama Anda (app_toko.py)
# Pastikan jalur import ini benar.
try:
    from app_toko import init_db
except ImportError:
    # Kasus darurat jika import gagal, tampilkan pesan
    print("Gagal mengimpor fungsi 'init_db' dari 'app_toko'. Pastikan nama file dan fungsi sudah benar.")
    exit(1)

print("--- Menjalankan Proses Inisiasi Database Render ---")
init_db()
print("--- Proses Inisiasi Database Selesai ---")

# Catatan: Fungsi init_db() di app_toko.py harus dipastikan sudah
# menggunakan 'with toko_app.app_context():' agar bisa dijalankan di luar rute Flask.