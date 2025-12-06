import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app_toko import toko_app, db

with toko_app.app_context():
    db.create_all()
    print("Database initialized ✅")