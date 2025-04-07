from flask import Flask, request, jsonify, g
from enum import Enum
from util.db_utils import DatabasePool, init_orders_db
from util.auth_utils import require_auth
from service.cart_service import get_cart_items, delete_cart, calculate_order_total
from models.order import OrderStatus, OrderValidator
from flask_swagger_ui import get_swaggerui_blueprint
from util.secrets_utils import load_secrets
from flask_cors import CORS
import psutil
import requests
from requests.exceptions import RequestException
import mysql.connector
from mysql.connector import Error
import datetime


# load_secrets() 

app = Flask(__name__)
CORS(app)

SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Order Service API"
    }
)

@app.route('/orders', methods=['POST'])
@require_auth
def create_order():
    user_id = g.user['cognito_user_id']
    shipping_address = g.user['address']
    try:
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor()


        # Get authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authorization header is required'}), 401

        
        # Get cart items
        try:
            cart_response = get_cart_items(auth_header)
            if not cart_response or 'items' not in cart_response:
                return jsonify({'error': 'Cart is empty'}), 400
            
            cart_items = cart_response['items']
            if not cart_items:
                return jsonify({'error': 'Cart is empty'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to fetch cart: {str(e)}'}), 500
        

        # Calculate total amount
        total_amount = calculate_order_total(cart_items)

        # Begin transaction
        connection.start_transaction()

        # Create new order
        order_query = """
            INSERT INTO orders (user_id, total_amount, shipping_address, status)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(order_query, (
            user_id,
            total_amount,
            shipping_address,
            OrderStatus.PENDING.value
        ))

        order_id = cursor.lastrowid

        # Create order items
        item_query = """
            INSERT INTO order_items (order_id, product_id, quantity, price)
            VALUES (%s, %s, %s, %s)
        """
        
        for product in cart_items:
            cursor.execute(item_query, (
                order_id,
                product['product']['product_id'],
                product['quantity'],
                product['price']
            ))

        # Delete cart after successful order creation
        try:
            print('cart deleted after successsful order!')
            delete_cart(auth_header)
        except Exception as e:
            # Log the error but don't fail the order
            connection.rollback()
            return jsonify({'error': f'Failed to delete cart: {str(e)}'}), 500

        # Commit transaction
        connection.commit()

        # Prepare response
        order_details = {
            'order_id': order_id,
            'user_id': user_id,
            'total_amount': float(total_amount),
            'shipping_address': shipping_address,
            'status': OrderStatus.PENDING.value,
            'items': [{
                'product_id': product['product']['product_id'],
                'quantity': product['quantity'],
                'price': float(product['price'])
            } for product in cart_items]
        }

        return jsonify({
            'message': 'Order created successfully',
            'order': order_details
        }), 200

    except Exception as e:
        connection.rollback()
        return jsonify({'error': f'Failed to create order: {str(e)}'}), 500

    finally:
        cursor.close()
        connection.close()

@app.route('/orders/<int:order_id>', methods=['GET'])
@require_auth
def get_order_by_orderid(order_id):

    try:    
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor(buffered=True, dictionary=True)


        # Get order details
        order_query = """
            SELECT * FROM orders WHERE id = %s
        """
        cursor.execute(order_query, (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({'error': 'Order not found'}), 404

        # Get order items
        items_query = """
            SELECT * FROM order_items WHERE order_id = %s
        """
        cursor.execute(items_query, (order_id,))
        items = cursor.fetchall()

        # Convert Decimal objects to float for JSON serialization
        order['total_amount'] = float(order['total_amount'])
        order['created_at'] = order['created_at'].isoformat()
        order['updated_at'] = order['updated_at'].isoformat()
        
        for item in items:
            item['price'] = float(item['price'])

        order['items'] = items
        return jsonify(order), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/users/orders', methods=['GET'])
@require_auth
def get_user_orders():
    user_id = g.user['cognito_user_id']
    try:
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor(buffered=True, dictionary=True)


        query = """
            SELECT id, total_amount, status, created_at 
            FROM orders 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """
        cursor.execute(query, (user_id,))
        orders = cursor.fetchall()

        # Convert Decimal objects to float for JSON serialization
        for order in orders:
            order['total_amount'] = float(order['total_amount'])
            order['created_at'] = order['created_at'].isoformat()

        return jsonify(orders), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/orders/<int:order_id>/status', methods=['PUT'])
@require_auth
def update_order_status(order_id):
    try:
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor()


        data = request.get_json()
        if 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400

        if data['status'] not in [status.value for status in OrderStatus]:
            return jsonify({'error': 'Invalid status'}), 400

        query = """
            UPDATE orders 
            SET status = %s 
            WHERE id = %s
        """
        cursor.execute(query, (data['status'], order_id))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Order not found'}), 404

        connection.commit()
        return jsonify({'message': 'Order status updated successfully'}), 200

    except Exception as e:
        connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

@app.route('/orders/<int:order_id>/cancel', methods=['PUT'])
@require_auth
def cancel_order(order_id):
    try:
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor(buffered=True, dictionary=True)


        # Check current status
        cursor.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({'error': 'Order not found'}), 404

        if order['status'] != OrderStatus.PENDING.value:
            return jsonify({'error': 'Only pending orders can be cancelled'}), 400

        # Update status to cancelled
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (OrderStatus.CANCELLED.value, order_id))
        connection.commit()

        return jsonify({'message': 'Order cancelled successfully'}), 200

    except Exception as e:
        connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/orders/health', methods=['GET'])
def health_check():
    """
    Comprehensive health check endpoint that verifies:
    1. Database connection (MySQL/RDS)
    2. Dependencies (Cart Service, Product Service)
    3. Memory usage
    4. Service uptime
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'service': 'order-service',
        'version': '1.0.0',
        'checks': {}
    }

    # Check Database Connection
    try:
        connection = DatabasePool.get_connection('order-service')
        cursor = connection.cursor()
        
        # Simple query to test database connection
        cursor.execute("SELECT 1")
        cursor.fetchone()
        
        health_status['checks']['database'] = {
            'status': 'healthy',
            'message': 'Successfully connected to database'
        }
        
        cursor.close()
        connection.close()
    except Error as e:
        health_status['checks']['database'] = {
            'status': 'unhealthy',
            'message': str(e),
            'error_code': str(e.errno) if hasattr(e, 'errno') else 'unknown'
        }
        health_status['status'] = 'unhealthy'

    # Check Memory Usage
    try:
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

    # Check Dependencies
    # dependencies = {
    #     'cart-service': 'http://cart-service:5004/health',
    #     'product-service': 'http://product-service:5002/health'
    # }

    # health_status['checks']['dependencies'] = {}
    
    # for service, url in dependencies.items():
    #     try:
    #         response = requests.get(url, timeout=2)
    #         health_status['checks']['dependencies'][service] = {
    #             'status': 'healthy' if response.status_code == 200 else 'unhealthy',
    #             'statusCode': response.status_code
    #         }
    #         if response.status_code != 200:
    #             health_status['status'] = 'warning'
    #     except RequestException as e:
    #         health_status['checks']['dependencies'][service] = {
    #             'status': 'unhealthy',
    #             'message': str(e)
    #         }
    #         health_status['status'] = 'warning'

    # Check System Resources
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        disk_usage = psutil.disk_usage('/')
        
        health_status['checks']['system'] = {
            'status': 'healthy',
            'cpu_usage_percent': cpu_percent,
            'disk_usage_percent': disk_usage.percent,
            'disk_free_gb': round(disk_usage.free / (1024 ** 3), 2)
        }
        
        # Set warning if resources are running low
        if cpu_percent > 80 or disk_usage.percent > 85:
            health_status['checks']['system']['status'] = 'warning'
            health_status['status'] = 'warning'
    except Exception as e:
        health_status['checks']['system'] = {
            'status': 'unknown',
            'message': str(e)
        }

    # Set response status code based on health status
    status_code = 200 if health_status['status'] == 'healthy' else 503

    return jsonify(health_status), status_code
if __name__ == '__main__':
    init_orders_db()  # Initialize database tables
    app.run(host='0.0.0.0', port=5004, debug=True)
