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
                if os.environ.get('rds_secret') is None:
                    os.environ['rds_secret'] = json.dumps(get_secret(f"rds!db-d0086fff-7ec8-427d-8070-d6001b9308aa"))

                secret = json.loads(os.environ.get('rds_secret'))

                logger.info('Initializing database connection pool')
                
                dbconfig = {
                    "pool_name": "user-service-pool",
                    "pool_size": 10,  # Reduced pool size
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

def init_user_db():
    """Initialize user database tables"""
    try:
        with get_db_connection() as conn:
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
            logger.info("User database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize user database: {e}")
        raise DatabaseError(f"Database initialization error: {str(e)}")
