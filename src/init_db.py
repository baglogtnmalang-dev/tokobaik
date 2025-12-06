# D:\G\Aplikasikoe\src\init_db.py
import sys, os

# Tambahkan folder root project ke sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app_toko import toko_app, db

with toko_app.app_context():
    db.create_all()
    print("Database initialized ✅")