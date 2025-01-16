from flask import Blueprint, jsonify, request, make_response
from sqlalchemy.exc import SQLAlchemyError
from models import Product, db

product_blueprint = Blueprint('product_api_routes', __name__, url_prefix='/api/product')

def create_response(message, result=None, status=200):
    response = {'message': message}
    if result is not None:
        response['result'] = result
    return make_response(jsonify(response), status)


@product_blueprint.route('/welcome', methods=['GET'])
def welcome_all_users():
    return create_response('Welcome product service')

def serialize_products(products):
    return [product.serialize() for product in products]

def commit_to_db(instance, success_message, failure_message):
    try:
        db.session.add(instance)
        db.session.commit()
        return jsonify({'message': success_message, 'result': instance.serialize()}), 201
    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()
        return jsonify({'message': failure_message}), 500

@product_blueprint.route('/all', methods=['GET'])
def get_all_products():
    all_products = Product.query.all()
    result = serialize_products(all_products)
    return jsonify({"result": result}), 200

@product_blueprint.route('/create', methods=['POST'])
def create_product():
    product = Product(
        name=request.form['name'],
        slug=request.form['slug'],
        image=request.form['image'],
        price=request.form['price']
    )
    return commit_to_db(product, 'Product Created', 'Product creation failed')

@product_blueprint.route('/<slug>', methods=['GET'])
def product_details(slug):
    product = Product.query.filter_by(slug=slug).first()
    if product:
        return jsonify({"result": product.serialize()}), 200
    return jsonify({"message": "No products found"}), 404

@product_blueprint.route('/update/<slug>', methods=['PUT'])
def update_product(slug):
    product = Product.query.filter_by(slug=slug).first()
    curr_version = product.version
    if not product:
        return jsonify({'message': 'Product not found'}), 404

    if curr_version != int(request.form['version']):
        return jsonify({'message': 'Conflict detected. The product has been modified by another transaction.'}), 409

    product.name=request.form['name']
    product.slug=request.form['slug']
    product.image=request.form['image']
    product.price=request.form['price']
    product.version=curr_version + 1
    db.session.commit()
    return jsonify({'message': 'Product updated', 'result': product.serialize()}), 200