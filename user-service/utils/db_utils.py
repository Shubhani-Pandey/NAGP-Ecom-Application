# utils/db_utils.py
import mysql.connector
from mysql.connector import pooling
from utils.secrets_utils import get_secret
from utils.circuit_breaker import circuit_breaker
import json
import os

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

class DatabasePool:
    _pool = None
    
    @classmethod
    def get_pool(cls, service_name):
        if cls._pool is None:
            try:
                if os.environ.get('rds_secret')=='':
                    os.environ['rds_secret'] = get_secret(f"rds!db-d0086fff-7ec8-427d-8070-d6001b9308aa")   

                secret = json.loads(os.environ.get('rds_secret'))

                print('got db configs, attempting db connection')
                
                dbconfig = {
                    "pool_name": f"{service_name}-pool",
                    "pool_size": 5,
                    "host": 'ecom-database.cfwys6mggqd4.eu-north-1.rds.amazonaws.com',
                    "user": secret['username'],
                    "password": secret['password'],
                    "database": 'ecommerce',
                    "port": 3306
                }
                
                cls._pool = mysql.connector.pooling.MySQLConnectionPool(**dbconfig)
                print('db connection succssful')

            except mysql.connector.Error as err:
                if err.errno == 2003:
                    print("Cannot connect to MySQL server. Check if server is running")
                elif err.errno == 1045:
                    print("Invalid username or password")
                elif err.errno == 1049:
                    print("Database does not exist")
                else:
                    print(f"Error: {err}")
                raise
        return cls._pool
    
    @classmethod
    @circuit_breaker('database-connection', failure_threshold=5, reset_timeout=60,fallback_function=lambda: None)
    def get_connection(cls, service_name):
        return cls.get_pool(service_name).get_connection()

def init_user_db():
    conn = None
    cursor = None

    """Initialize user database tables"""
    try:
        conn = DatabasePool.get_connection('user-service')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                cognito_user_id VARCHAR(36) UNIQUE NOT NULL,
                username VARCHAR(80) UNIQUE NOT NULL,
                name VARCHAR(100),
                email VARCHAR(120) UNIQUE NOT NULL,
                phone VARCHAR(20),
                gender VARCHAR(10),
                address TEXT,
                birthdate DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
        ''')
        conn.commit()
    except Exception as e:
        raise DatabaseError(f"Database initialization error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
