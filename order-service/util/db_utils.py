# utils/db_utils.py
import mysql.connector
from mysql.connector import pooling
from util.secrets_utils import get_secret
from util.circuit_breaker import circuit_breaker
from contextlib import contextmanager
import os
import json
import logging
logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

class DatabaseConnection:
    _instance = None
    _db_pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._db_pool:
            self._db_pool = DatabasePool()

    def get_connection(self):
        """Get connection from the pool"""
        return self._db_pool.get_pool()

class DatabasePool:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    def _initialize_pool(self):
        """Initialize the connection pool if not already initialized"""
        if self._pool is None:
            try:
                if os.environ.get('rds_secret')=='':
                    os.environ['rds_secret'] = get_secret(f"rds!db-d0086fff-7ec8-427d-8070-d6001b9308aa")   

                secret = json.loads(os.environ.get('rds_secret'))

                logger.info('Initializing database connection pool')
                
                dbconfig = {
                    "pool_name": "order-service-pool",
                    "pool_size": 3,  # Reduced pool size
                    "host": 'ecom-database.cfwys6mggqd4.eu-north-1.rds.amazonaws.com',
                    "user": secret['username'],
                    "password": secret['password'],
                    "database": 'ecommerce',
                    "port": 3306,
                    "pool_reset_session": True,
                    "autocommit": True,
                    "connect_timeout": 10
                }
                
                self._pool = mysql.connector.pooling.MySQLConnectionPool(**dbconfig)
                logger.info("Database pool initialized successfully")
            except mysql.connector.Error as err:
                if err.errno == 2003:
                    logger.error("Cannot connect to MySQL server. Check if server is running")
                elif err.errno == 1045:
                    logger.error("Invalid username or password")
                elif err.errno == 1049:
                    logger.error("Database does not exist")
                else:
                    logger.error(f"Error: {err}")
                raise DatabaseError(f"Database initialization error: {str(err)}")

    def get_pool(self):
        """Get the connection pool"""
        if not self._pool:
            self._initialize_pool()
        return self._pool

@contextmanager
@circuit_breaker('database-connection', failure_threshold=5, reset_timeout=60,fallback_function=lambda: None)
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        db = DatabaseConnection()
        pool = db.get_connection()
        conn = pool.get_connection()
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise DatabaseError(f"Database connection error: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {str(e)}")

def init_orders_db():
    """Initialize ordera database tables"""
    try:
        with get_db_connection() as conn:
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
