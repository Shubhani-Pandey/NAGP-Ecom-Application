from flask import Flask, request, jsonify, g
from flask_cors import CORS
from models.cart import CartModel
from flask_swagger_ui import get_swaggerui_blueprint
from util.metrics import MetricsCollector
from util.db_utils import init_dynamodb
from util.auth_utils import require_auth
from util.error_handling import handle_exceptions
from util.secrets_utils import load_secrets
from datetime import datetime
import logging

# load_secrets() 

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Swagger configuration
SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Cart Service API"
    }
)

@app.route('/cart', methods=['POST'])
@require_auth
@handle_exceptions
def create_cart():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    CartModel.validate_cart_data(data)
    user_id = g.user['cognito_user_id']

    print(user_id, data)
    
    return CartModel.create_cart(user_id, data)

@app.route('/cart/user_cart', methods=['GET'])
@require_auth
@handle_exceptions
def get_cart():
    print('inside get cart api')
    user_id = g.user['cognito_user_id']
    return CartModel.get_cart_by_user_id(user_id)

@app.route('/cart', methods=['PUT'])
@require_auth
@handle_exceptions
def update_cart():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    CartModel.validate_cart_data(data)
    user_id = g.user['cognito_user_id']
    
    return CartModel.update_cart(user_id, data)

@app.route('/cart/<product_id>', methods=['DELETE'])
@require_auth
@handle_exceptions
def delete_from_cart(product_id):
    if not product_id:
        return jsonify({'error': 'Product ID is required'}), 400
        
    user_id = g.user['cognito_user_id']
    return CartModel.delete_item(user_id, product_id)

@app.route('/cart', methods=['DELETE'])
@require_auth
@handle_exceptions
def delete_cart():

    user_id = g.user['cognito_user_id']
    return CartModel.delete_cart(user_id)

@app.route('/cart/metrics/circuit-breakers', methods=['GET'])
@handle_exceptions
def circuit_breaker_metrics():
    try:
        minutes = int(request.args.get('minutes', 5))
        if minutes < 1:
            return jsonify({'error': 'Minutes must be greater than 0'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid minutes parameter'}), 400
        
    events = MetricsCollector().get_recent_events(minutes)
    return jsonify([{
        'circuit_name': e.circuit_name,
        'state': e.state,
        'timestamp': e.timestamp.isoformat(),
        'failure_count': e.failure_count
    } for e in events])

@app.route('/cart/health', methods=['GET'])
def health_check():
    try:
        # Add any necessary health checks here
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'cart-service'
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'cart-service'
        }), 500

@app.route('/', methods=['GET'])
def welcome():
    return "Welcome cart-service"

# Error handlers for common HTTP errors
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request'}), 400

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Unauthorized'}), 401

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    init_dynamodb()
    app.run(host='0.0.0.0', port=5003, debug=True)
