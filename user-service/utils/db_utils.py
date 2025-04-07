# utils/db_utils.py
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling
from utils.secrets_utils import get_secret
from utils.circuit_breaker import circuit_breaker
import json
import logging
import os

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

class DatabaseConnection:
    def __init__(self):
        self.db_pool = DatabasePool()._pool

    def get_connection(self):
        return self.db_pool
    

class DatabasePool:
    _instance = None
    _pool = None

    def __init__(self):
        if self._instance is None:
            self._instance = super(DatabasePool, self).__new__(self)
            self._instance._initialize_pool()
        return self._instance

    def _initialize_pool(self):
        try:

            if os.environ.get('rds_secret')=='':
                    os.environ['rds_secret'] = get_secret(f"rds!db-d0086fff-7ec8-427d-8070-d6001b9308aa")   

            secret = json.loads(os.environ.get('rds_secret'))

            print('got db configs, attempting db connection')
            
            dbconfig = {
                "pool_name": "user-service-pool",
                "pool_size": 5,
                "host": 'ecom-database.cfwys6mggqd4.eu-north-1.rds.amazonaws.com',
                "user": secret['username'],
                "password": secret['password'],
                "database": 'ecommerce',
                "port": 3306
            }
                
            
            self._pool = mysql.connector.pooling.MySQLConnectionPool(**dbconfig)
            logger.info("Database pool initialized successfully")
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


def init_user_db():
    conn = None
    cursor = None

    """Initialize user database tables"""
    try:
        # conn = DatabasePool.get_connection('user-service')
        # cursor = conn.cursor()
        with DatabaseConnection().get_connection() as conn:
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
