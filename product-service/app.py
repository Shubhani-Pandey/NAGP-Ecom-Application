import datetime
from flask import Flask, request, jsonify
from botocore.exceptions import ClientError
from flask_cors import CORS
from util.db_utils import init_dynamodb
from decimal import Decimal
from util.metrics import MetricsCollector
from model.product import ProductModel
from util.auth_utils import require_auth
from flask_swagger_ui import get_swaggerui_blueprint
from util.secrets_utils import load_secrets
from http import HTTPStatus
from model.product_search import SearchAPI
from flask_caching import Cache
import json


SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

cache_config = {
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching default is SimpleCache
    "CACHE_DEFAULT_TIMEOUT": 300  # 5 minutes default timeout
}

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Product Service API"
    }
)

# load_secrets() 

app = Flask(__name__)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
cache = Cache(app, config=cache_config)
CORS(app)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)
    
@app.route('/products', methods=['POST'])
@require_auth
def create_product():
    data = request.get_json()

    for product in data:
        # Create in DynamoDB
        ProductModel.create_product(product)
        # Index in OpenSearch
        ProductModel.index_product(product)
    
    cache.delete_memoized(get_products)
    return jsonify({'message': 'Product created successfully'})       

@app.route('/products', methods=['GET'])
@cache.cached(timeout=300)
def get_products():
    items = ProductModel.get_all_products()
    # Convert Decimal to float for JSON response
    products = json.loads(json.dumps(items, cls=DecimalEncoder))
    return jsonify(products)

@app.route('/productsbycategory/<string:category>', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_products_by_category(category):
    print(category)
    items = ProductModel.get_all_products(category)
    # Convert Decimal to float for JSON response
    products = json.loads(json.dumps(items, cls=DecimalEncoder))
    return jsonify(products)

@app.route('/products/<string:product_id>', methods=['GET'])
@cache.memoize(timeout=300)
def get_product(product_id):
    item = ProductModel.get_product(product_id)
    # Convert Decimal to float for JSON response
    product = json.loads(json.dumps(item, cls=DecimalEncoder))
    print(product)
    return jsonify(product)

@app.route('/products/<string:product_id>', methods=['PUT'])
@require_auth
def update_product(product_id):
    try:
        data = request.get_json()
        updated_product = ProductModel.update_product(product_id, data)

        # Invalidate specific product cache
        cache.delete_memoized(get_product, product_id)
        # Invalidate products list cache
        cache.delete_memoized(get_products)

        return jsonify(json.loads(json.dumps(updated_product, cls=DecimalEncoder)))
        
    except ClientError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'exception': str(e)}), 500

@app.route('/products/<string:product_id>', methods=['DELETE'])
@require_auth
def delete_product(product_id):
    try:
        response= ProductModel.delete_product(product_id)
        # Invalidate caches
        cache.delete_memoized(get_product, product_id)
        cache.delete_memoized(get_products)
        return response
    except ClientError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products/<string:product_id>/stock', methods=['PATCH'])
@require_auth
def update_stock(product_id):
    try:
        data = request.get_json()
        if 'stock' not in data:
            return jsonify({'error': 'Stock value is required'}), 400
            
        response = ProductModel.update_stock(product_id, data['stock'])
        if response is not None:
            return jsonify({'message': 'Stock updated successfully' })
        return jsonify({'message': 'Product not found'}), 404
        
    except ClientError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products/search', methods=['GET'])
def search_products():
    try:
        # Get and validate parameters
        clean_params, error = SearchAPI().validate_search_params(request.args)
        print(clean_params, error)
        if error:
            return jsonify({
                'error': 'Invalid parameters',
                'message': error
            }), HTTPStatus.BAD_REQUEST

        # Perform search
        search_results = SearchAPI().product_search.search_products(clean_params)
        
        # Format response
        response = SearchAPI().format_response(search_results)

        # print(response)
        
        return jsonify(response), HTTPStatus.OK

    except Exception as e:
        return jsonify({
            'error': 'Search failed',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/products/suggest', methods=['GET'])
def suggest_products():
    """Get search suggestions"""
    try:
        prefix = request.args.get('q', '').strip()
        if not prefix:
            return jsonify({
                'error': 'Missing query parameter',
                'message': 'Query parameter "q" is required'
            }), HTTPStatus.BAD_REQUEST

        size = min(int(request.args.get('size', 10)), 10)
        
        suggestions = SearchAPI().product_search.suggest_products(prefix, size)

        print(suggestions)
        
        return jsonify({
            'suggestions': suggestions
        }), HTTPStatus.OK

    except Exception as e:
        return jsonify({
            'error': 'Suggestion failed',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/metrics/circuit-breakers', methods=['GET'])
def circuit_breaker_metrics():
    minutes = request.args.get('minutes', 5, type=int)
    events = MetricsCollector().get_recent_events(minutes)
    return jsonify([{
        'circuit_name': e.circuit_name,
        'state': e.state,
        'timestamp': e.timestamp.isoformat(),
        'failure_count': e.failure_count
    } for e in events])

@app.route('/cache/clear', methods=['POST'])
@require_auth
def clear_cache():
    try:
        cache.clear()
        return jsonify({'message': 'Cache cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
def welcome():
    return "Welcome product-service"

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'error': 'Not found',
        'message': 'The requested resource was not found'
    }), HTTPStatus.NOT_FOUND

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({
        'error': 'Method not allowed',
        'message': 'The method is not allowed for this endpoint'
    }), HTTPStatus.METHOD_NOT_ALLOWED

if __name__ == '__main__':
    init_dynamodb()
    app.run(host='0.0.0.0', port=5002, debug=True)