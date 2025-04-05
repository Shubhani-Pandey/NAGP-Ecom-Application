# utils/auth_utils.py
import jwt
from functools import wraps
from flask import request, jsonify
from utils.cognito_utils import CognitoClient

def validate_token(token):
    """Validate Cognito JWT token"""
    try:
        cognito = CognitoClient()
        headers = jwt.get_unverified_header(token)
        kid = headers['kid']
        keys = cognito.get_public_keys()
        
        if kid not in keys:
            raise ValueError('Invalid token key')
        
            
        public_key = keys[kid]

        # First decode without verification to check token type
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        
        # Get the token use type
        token_use = unverified_claims.get('token_use')
        client_id = cognito.get_config()['client_id']

        if token_use == 'access':
            # For access tokens, check client_id claim
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256']
            )
            # Manually verify client_id after decode
            if payload.get('client_id') != client_id:
                raise jwt.InvalidTokenError('Invalid client_id')
        else:
            # For ID tokens, verify audience
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                audience=client_id
            )
        return payload
    
    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return None
    except jwt.InvalidAudienceError:
        print("Invalid audience")
        return None
    except jwt.InvalidSignatureError:
        print("Signature verification failed")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token error: {str(e)}")
        return None


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401
        
        try:
            token = auth_header.split(' ')[1]
            payload = validate_token(token)
            if not payload:
                return jsonify({'error': 'Invalid token'}), 401
            
            # print('payload',payload)
            request.user = {
                'user_id': payload['sub'],
                'username': payload['username'],
                'email': payload.get('email','')
            }
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': str(e)}), 401
    return decorated
