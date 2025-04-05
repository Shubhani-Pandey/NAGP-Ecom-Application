from flask import Flask, request, jsonify, g
from functools import wraps
from botocore.exceptions import ClientError
from decimal import Decimal, InvalidOperation
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom error handling decorator
def handle_exceptions(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            
            if error_code == 'ResourceNotFoundException':
                return jsonify({'error': 'Resource not found'}), 404
            elif error_code == 'ValidationException':
                return jsonify({'error': 'Invalid request data'}), 400
            elif error_code == 'ProvisionedThroughputExceededException':
                return jsonify({'error': 'Service is currently experiencing high load'}), 429
            
            return jsonify({'error': 'Database operation failed'}), 500
            
        except ValueError as e:
            logger.error(f"Value error: {str(e)}")
            return jsonify({'error': 'Invalid input data'}), 400
            
        except InvalidOperation as e:
            logger.error(f"Decimal operation error: {str(e)}")
            return jsonify({'error': 'Invalid numeric value'}), 400
            
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper