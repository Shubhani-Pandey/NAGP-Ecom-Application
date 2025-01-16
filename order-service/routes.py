from flask import Blueprint, jsonify, request
import requests
from models import Order, OrderItem, db

order_blueprint = Blueprint('order_api_routes', __name__, url_prefix="/api/order")

USER_API_URL = 'http://user-service-c:5001/api/user'

def get_user(api_key):
    headers = {'Authorization': api_key}
    response = requests.get(USER_API_URL, headers=headers)
    if response.status_code != 200:
        return None
    return response.json().get('result')

def authenticate_user():
    api_key = request.headers.get('Authorization')
    if not api_key:
        return None, jsonify({'message': 'Not logged in'}), 401
    user = get_user(api_key)
    if not user:
        return None, jsonify({'message': 'Not logged in'}), 401
    return user, None, None

@order_blueprint.route('/', methods=['GET'])
def get_open_order():
    user, error_response, status_code = authenticate_user()
    if error_response:
        return error_response, status_code

    open_order = Order.query.filter_by(user_id=user['id'], is_open=True).first()
    if open_order:
        return jsonify({'result': open_order.serialize()}), 200
    return jsonify({'message': 'No open orders'}), 404

@order_blueprint.route('/all', methods=['GET'])
def all_orders():
    orders = Order.query.all()
    result = [order.serialize() for order in orders]
    return jsonify(result), 200

@order_blueprint.route('/add-item', methods=['POST'])
def add_order_item():
    user, error_response, status_code = authenticate_user()
    if error_response:
        return error_response, status_code

    product_id = int(request.form['product_id'])
    quantity = int(request.form['quantity'])

    open_order = Order.query.filter_by(user_id=user['id'], is_open=True).first()
    if not open_order:
        open_order = Order(user_id=user['id'], is_open=True)

    order_item = next((item for item in open_order.order_items if item.product_id == product_id), None)
    if order_item:
        order_item.quantity += quantity
    else:
        open_order.order_items.append(OrderItem(product_id=product_id, quantity=quantity))

    db.session.add(open_order)
    db.session.commit()
    return jsonify({"result": open_order.serialize()}), 200

@order_blueprint.route('/checkout', methods=['POST'])
def checkout():
    user, error_response, status_code = authenticate_user()
    if error_response:
        return error_response, status_code

    open_order = Order.query.filter_by(user_id=user['id'], is_open=True).first()
    if not open_order:
        return jsonify({'message': 'No open orders'}), 404

    open_order.is_open = False
    db.session.add(open_order)
    db.session.commit()
    return jsonify({'result': open_order.serialize()}), 200
