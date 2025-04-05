from flask import Flask, request, jsonify, g
from enum import Enum
from util.db_utils import DatabasePool, init_orders_db
from util.auth_utils import require_auth
from service.cart_service import get_cart_items, delete_cart, calculate_order_total
from models.order import OrderStatus, OrderValidator
from flask_swagger_ui import get_swaggerui_blueprint
from util.secrets_utils import load_secrets
from flask_cors import CORS


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

@app.route('/api/orders', methods=['POST'])
@require_auth
def create_order():
    user_id = g.user['cognito_user_id']
    shipping_address = g.user['address']
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

    try:
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

@app.route('/api/orders/<int:order_id>', methods=['GET'])
@require_auth
def get_order_by_orderid(order_id):
    
    connection = DatabasePool.get_connection('order-service')
    cursor = connection.cursor(buffered=True, dictionary=True)

    try:
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

@app.route('/api/users/orders', methods=['GET'])
@require_auth
def get_user_orders():
    user_id = g.user['cognito_user_id']
    connection = DatabasePool.get_connection('order-service')
    cursor = connection.cursor(buffered=True, dictionary=True)

    try:
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

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@require_auth
def update_order_status(order_id):
    connection = DatabasePool.get_connection('order-service')
    cursor = connection.cursor()

    try:
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

@app.route('/api/orders/<int:order_id>/cancel', methods=['PUT'])
@require_auth
def cancel_order(order_id):
    connection = DatabasePool.get_connection('order-service')
    cursor = connection.cursor(buffered=True, dictionary=True)

    try:
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

if __name__ == '__main__':
    init_orders_db()  # Initialize database tables
    app.run(host='0.0.0.0', port=5004, debug=True)
