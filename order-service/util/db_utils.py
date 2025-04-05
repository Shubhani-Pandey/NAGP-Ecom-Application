# utils/db_utils.py
import mysql.connector
from mysql.connector import pooling
from util.secrets_utils import get_secret
from util.circuit_breaker import circuit_breaker
import os
import json

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

class DatabasePool:
    _pool = None
    
    @classmethod
    def get_pool(cls, service_name):
        if cls._pool is None:
            if os.environ.get('rds_secret')=='':
                os.environ['rds_secret'] = get_secret(f"rds!db-d0086fff-7ec8-427d-8070-d6001b9308aa") 

            secret = json.loads(os.environ.get('rds_secret'))
            
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
        return cls._pool
    
    @classmethod
    @circuit_breaker('database-connection', failure_threshold=5, reset_timeout=60,fallback_function=lambda: None)
    def get_connection(cls, service_name):
        return cls.get_pool(service_name).get_connection()

def init_orders_db():
    """Initialize ordera database tables"""
    try:
        conn = DatabasePool.get_connection('order-service')
        cursor = conn.cursor()
        # Create orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                total_amount DECIMAL(10, 2) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                shipping_address VARCHAR(500) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id)
            )
        """)

        # Create order_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id INT NOT NULL,
                product_id VARCHAR(20) NOT NULL,
                quantity INT NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                INDEX idx_order_id (order_id),
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        print("Database tables created successfully")
    except Exception as e:
        conn.rollback()
        raise DatabaseError(f"Database initialization error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
