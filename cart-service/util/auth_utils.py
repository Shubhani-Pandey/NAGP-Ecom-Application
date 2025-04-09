from functools import wraps
from flask import request, jsonify, g
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_service_url = 'http://user-service-ecs-connect:5001'
# user_service_url = 'http://127.0.0.1:5001'
def get_auth_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    return auth_header.split(' ')[1]

def validate_token_with_user_service(token):
    """Validates token with user service and returns user details"""
    try:
        # logger.info('making request to user service with token as :', token)
        # logger.info('making request to:',f"{user_service_url}/users/me")
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f"{user_service_url}/users/me",headers=headers)
        # logger.info(response)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error validating token: {str(e)}")
        return None

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_auth_token()
        
        if not token:
            return jsonify({'error': 'No authorization token provided'}), 401
            
        user_data = validate_token_with_user_service(token)
        # logger.info('validated user data',user_data)
        
        if not user_data:
            return jsonify({'error': 'Invalid or expired token'}), 401
            
        # Add user data to flask.g for use in the route
        g.user = user_data
        # logger.info('flask.g user data',g.user)
        return f(*args, **kwargs)
    return decorated_function
