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
from util.secrets_utils import get_secret
from http import HTTPStatus
from model.product_search import SearchAPI
from flask_caching import Cache
import json
import boto3
import os
from opensearchpy import OpenSearch


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

@app.route('/products/metrics/circuit-breakers', methods=['GET'])
def circuit_breaker_metrics():
    minutes = request.args.get('minutes', 5, type=int)
    events = MetricsCollector().get_recent_events(minutes)
    return jsonify([{
        'circuit_name': e.circuit_name,
        'state': e.state,
        'timestamp': e.timestamp.isoformat(),
        'failure_count': e.failure_count
    } for e in events])

@app.route('/products/cache/clear', methods=['POST'])
@require_auth
def clear_cache():
    try:
        cache.clear()
        return jsonify({'message': 'Cache cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products/health', methods=['GET'])
def health_check():
    """
    Comprehensive health check endpoint that verifies:
    1. DynamoDB connection
    2. OpenSearch connection
    3. Memory usage
    4. Service uptime
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'service': 'product-service',
        'version': '1.0.0',  # You can make this dynamic
        'checks': {}
    }

    # Check DynamoDB
    try:
        if os.environ.get('dynamo_db_secret')=='':
            os.environ['dynamo_db_secret'] = get_secret(f"dev/dynamodb/config") 

        secret = json.loads(os.environ.get('dynamo_db_secret'))

        dynamodb = boto3.client('dynamodb',
                                  region_name=secret['region'],
                                  aws_access_key_id=secret['AWS_ACCESS_KEY_ID'],
                                  aws_secret_access_key=secret['AWS_SECRET_ACCESS_KEY'])
        
        dynamodb.describe_table(TableName='Products')
        health_status['checks']['dynamodb'] = {
            'status': 'healthy',
            'message': 'Successfully connected to DynamoDB'
        }
    except ClientError as e:
        health_status['checks']['dynamodb'] = {
            'status': 'unhealthy',
            'message': str(e),
            'error_code': e.response['Error']['Code']
        }
        health_status['status'] = 'unhealthy'

    # Check OpenSearch
    try:
        if os.environ.get('opensearch_secret')=='':
                os.environ['opensearch_secret'] = get_secret('opensearch/config') 

        secrets = json.loads(os.environ.get('opensearch_secret'))
        host = secrets.get('host')
        region = secrets.get('region')
        master_user_name = secrets.get('master_user_name')
        master_user_password = secrets.get('master_user_password')
        
        opensearch_client = OpenSearch(
            hosts=[{
                'host': host,
                'port': 443
            }],
            http_auth=(
                master_user_name,
                master_user_password
            ),
            use_ssl=True,
            verify_certs=True
        )
        opensearch_health = opensearch_client.cluster.health()
        health_status['checks']['opensearch'] = {
            'status': 'healthy' if opensearch_health['status'] in ['green', 'yellow'] else 'unhealthy',
            'message': f"Cluster status: {opensearch_health['status']}"
        }
        if opensearch_health['status'] == 'red':
            health_status['status'] = 'unhealthy'
    except Exception as e:
        health_status['checks']['opensearch'] = {
            'status': 'unhealthy',
            'message': str(e)
        }
        health_status['status'] = 'unhealthy'

    # Check Memory Usage
    try:
        import psutil
        memory = psutil.Process().memory_info()
        memory_usage_mb = memory.rss / 1024 / 1024  # Convert to MB
        memory_threshold_mb = 500  # Set your threshold

        health_status['checks']['memory'] = {
            'status': 'healthy' if memory_usage_mb < memory_threshold_mb else 'warning',
            'usage_mb': round(memory_usage_mb, 2),
            'threshold_mb': memory_threshold_mb
        }
        if memory_usage_mb >= memory_threshold_mb:
            health_status['status'] = 'warning'
    except Exception as e:
        health_status['checks']['memory'] = {
            'status': 'unknown',
            'message': str(e)
        }

    # Check Cache Status
    try:
        # Test cache by setting and getting a value
        test_key = 'health_check_test'
        test_value = 'test_value'
        
        cache.set(test_key, test_value, timeout=10)
        cached_value = cache.get(test_key)
        
        cache_status = 'healthy' if cached_value == test_value else 'unhealthy'
        cache_message = 'Cache is working properly' if cache_status == 'healthy' else 'Cache read/write test failed'
        
        health_status['checks']['cache'] = {
            'status': cache_status,
            'message': cache_message
        }
        
        if cache_status == 'unhealthy':
            health_status['status'] = 'warning'
            
    except Exception as e:
        health_status['checks']['cache'] = {
            'status': 'unhealthy',
            'message': f'Cache error: {str(e)}'
        }
        health_status['status'] = 'warning'

    # Add Dependencies Check
    dependencies = {
        'user-service': 'http://user-service-ecs-connect:5001/users/health',
        'order-service': 'http://order-service-ecs-connect:5003/orders/health'
    }

    health_status['checks']['dependencies'] = {}
    import requests
    from requests.exceptions import RequestException

    for service, url in dependencies.items():
        try:
            response = requests.get(url, timeout=2)
            health_status['checks']['dependencies'][service] = {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'statusCode': response.status_code
            }
        except RequestException as e:
            health_status['checks']['dependencies'][service] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'warning'

    # Set response status code based on health status
    status_code = 200 if health_status['status'] == 'healthy' else 503

    return jsonify(health_status), status_code

@app.route('/', methods=['GET'])
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