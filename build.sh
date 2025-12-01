#!/usr/bin/env bash

# 1. Install dependencies
pip install -r requirements.txt

# 2. Run database creation command (Using a function for stability)
python -c '
from app_toko import toko_app, db

def create_db_tables():
    with toko_app.app_context():
        # db.create_all() akan membuat semua tabel di PostgreSQL
        db.create_all()

create_db_tables()
'