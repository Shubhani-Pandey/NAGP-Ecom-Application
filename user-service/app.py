import boto3
from flask import Flask, request, jsonify
from utils.auth_utils import require_auth
from utils.cognito_utils import CognitoClient, CognitoError
from utils.db_utils import init_user_db
from models.user import UserModel
from flask_swagger_ui import get_swaggerui_blueprint
from utils.rate_limit import setup_limiter
from utils.db_utils import  DatabasePool, DatabaseError
from utils.circuit_breaker import CircuitBreakerRegistry
from utils.metrics import MetricsCollector
from flask_cors import CORS
from botocore.exceptions import ClientError
import logging
import os

logger = logging.getLogger(__name__)

SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "User Service API"
    }
)

# load_secrets()

app = Flask(__name__)
cognito = CognitoClient()
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
CORS(app)

# Initialize rate limiter
limiter = setup_limiter(app)

@app.route('/auth/register', methods=['POST'])
def register_user():
    print("Content-Type:", request.headers.get('Content-Type'))
    print("Raw Data:", request.get_data(as_text=True))
    try:
        data = request.get_json()
        
        # Register user in Cognito
        response = cognito.register_user(
            data['username'],
            data['password'],
            data['email'],
            data['phoneNumber'],
            data['gender'],
            data['address'],
            data['birthdate'],
            data['name']
        )
        
        try:
            # Store user in database
            UserModel.create_user(response['UserSub'], data)
        except DatabaseError as db_err:
            # Handle database error
            logger.error(f"Database error: {db_err}")
        except CognitoError as auth_err:
            # Handle authentication error
            logger.error(f"Cognito error: {auth_err}")
        
        return jsonify({
            'message': 'User registered successfully',
            'user_id': response['UserSub']
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/confirm', methods=['POST'])
def confirm_registration():
    try:
        data = request.get_json()
        cognito.confirm_registration(data['username'], data['code'])
        return jsonify({'message': 'User confirmed successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/auth/login', methods=['POST'])
# @limiter.limit("50 per minute")
def login():
    try:
        data = request.get_json()
        print(data)
        auth_result = cognito.login(data['username'], data['password'])

        
        return jsonify({
            'access_token': auth_result['AccessToken'],
            'id_token': auth_result['IdToken'],
            'refresh_token': auth_result['RefreshToken']
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 401

@app.route('/auth/resend-code', methods=['POST'])
def resend_confirmation_code():
    try:
        data = request.get_json()
        if not data or 'username' not in data:
            return jsonify({"error": "Username is required"}), 400

        client = boto3.client('cognito-idp')
        response = client.resend_confirmation_code(
            ClientId='7fuk2g86cq43ctmpkgauganm3v',
            Username=data['username']
        )

        return jsonify({
            "message": "Confirmation code resent successfully",
            "delivery_details": response.get('CodeDeliveryDetails', {})
        }), 200

    except CognitoError as e:
        return jsonify({
            "error": f"Cognito error: {str(e)}"
        }), 400
    
@app.route('/auth/logout', methods=['POST'])
@require_auth
def logout():
    try:
        auth_header = request.headers.get('Authorization')
        token = auth_header.split(' ')[1]
        cognito.logout(token)
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/users/me', methods=['GET'])
@require_auth
def get_current_user():
    print('in get current user')
    try:
        # Get access token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid authorization header'}), 401
        
        access_token = auth_header.split(' ')[1]
        
        # Get user details from Cognito using access token
        try:
            cognito_user = cognito.client.get_user(AccessToken=access_token)
            
            # Convert Cognito attributes to dictionary
            cognito_attributes = {
                attr['Name']: attr['Value'] 
                for attr in cognito_user['UserAttributes']
            }

            # Get user sub (Cognito user ID) from attributes
            user_sub = cognito_attributes.get('sub')

            # print('cognito_user',cognito_user)
            # print('cognito_attributes', cognito_attributes)
            # print('user_sub',user_sub)
            
            # Get user from database using Cognito sub
            db_user = UserModel.get_user_by_cognito_id(user_sub)

            # if not db_user:
            #     return jsonify({"message":"User not found"}), 401
            
        
            # Combine database and Cognito user information
            user_info = {
                **(db_user or {}),
                'cognito_id': user_sub,
                'username': cognito_user['Username'],
                'email': cognito_attributes.get('email'),
                'phone_number': cognito_attributes.get('phone_number'),
                'name': (cognito_attributes.get('name') or str(cognito_attributes.get('email')).split('@')[0]),
                'email_verified': cognito_attributes.get('email_verified'),
                'phone_verified': cognito_attributes.get('phone_number_verified'),
                # Add any other relevant attributes you need
            }
            
            return jsonify(user_info), 200

        except cognito.client.exceptions.NotAuthorizedException as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401
        except Exception as cognito_error:
            logger.error(f"Error fetching Cognito user details: {str(cognito_error)}")
            return jsonify({'error': 'Failed to fetch user details'}), 500

    except Exception as e:
        logger.error(f"Error in get_current_user: {str(e)}")
        print(e)
        return jsonify({'error': 'Internal server error'}), 500
    
@app.route('/users/me', methods=['PUT'])
@require_auth
def update_user():
    try:
        data = request.get_json()
        success = UserModel.update_user(request.user['user_id'], data)
        if success:
            return jsonify({'message': 'User updated successfully'}), 200
        return jsonify({'message': 'No updates performed'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('users/health', methods=['GET'])
def health_check():
    # Get all circuit breaker states
    circuit_states = CircuitBreakerRegistry().get_all_states()
    
    # Check individual service health
    db_healthy = False
    cognito_healthy = False
    
    try:
        conn = DatabasePool.get_connection('user-service')
        conn.ping()
        db_healthy = True
    except:
        logger.error(f"Database health: {db_healthy}")

    try:
        cognito = CognitoClient()
        cognito_healthy = cognito.client is not None
    except:
        logger.error(f"Cognito Health: {cognito_healthy}")

    status = 200 if db_healthy and cognito_healthy else 503
    
    return jsonify({
        'database': {
            'status': 'healthy' if db_healthy else 'unhealthy',
            'circuit_state': circuit_states.get('database-connection', 'UNKNOWN')
        },
        'cognito': {
            'status': 'healthy' if cognito_healthy else 'unhealthy',
            'login_circuit': circuit_states.get('cognito-login', 'UNKNOWN'),
            'register_circuit': circuit_states.get('cognito-register', 'UNKNOWN')
        }
    }), status


@app.route('users/metrics/circuit-breakers', methods=['GET'])
def circuit_breaker_metrics():
    minutes = request.args.get('minutes', 5, type=int)
    events = MetricsCollector().get_recent_events(minutes)
    return jsonify([{
        'circuit_name': e.circuit_name,
        'state': e.state,
        'timestamp': e.timestamp.isoformat(),
        'failure_count': e.failure_count
    } for e in events])

if __name__ == '__main__':
    init_user_db()
    app.run(host='0.0.0.0', port=5001, debug=True)
