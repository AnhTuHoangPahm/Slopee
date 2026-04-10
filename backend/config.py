import os

class Config:
    # Database configuration 
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'slopee_db')
    
    # Secret Key (fallback to default string for local development)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-change-in-prod')
