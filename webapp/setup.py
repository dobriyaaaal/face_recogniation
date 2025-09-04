"""
Database Setup Script for Face Recognition System
Initializes SQLite database with encrypted storage
"""
import sqlite3
import os
import hashlib
from cryptography.fernet import Fernet

DB_PATH = 'secure_face_recognition.db'

def init_database():
    """Initialize the secure database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # People table with custom fields support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            age INTEGER,
            job_title TEXT,
            department TEXT,
            employee_id TEXT,
            phone TEXT,
            email TEXT,
            custom_field_1 TEXT,
            custom_field_2 TEXT,
            custom_field_3 TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_count INTEGER DEFAULT 0,
            notes TEXT
        )
    ''')
    
    # Person images table for multiple photos per person
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS person_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            image_data BLOB,
            image_name TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (person_id) REFERENCES people (id)
        )
    ''')
    
    # Streams table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            stream_type TEXT DEFAULT 'ip_camera',
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Camera streams table (for compatibility)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS camera_streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            stream_url TEXT NOT NULL,
            created_by INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Enhanced detections table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            person_name TEXT NOT NULL,
            confidence REAL NOT NULL,
            stream_name TEXT NOT NULL,
            detection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            detection_image BLOB,
            bbox_data TEXT,
            FOREIGN KEY (person_id) REFERENCES people (id)
        )
    ''')
    
    # Create default admin user
    salt = 'salt'
    password_hash = hashlib.pbkdf2_hmac('sha256', 'admin123'.encode(), salt.encode(), 100000).hex()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, salt)
        VALUES (?, ?, ?)
    ''', ('admin', password_hash, salt))
    
    conn.commit()
    conn.close()
    print('✅ Database initialized successfully!')

if __name__ == '__main__':
    init_database()
