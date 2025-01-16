from flask import Blueprint, jsonify, request, make_response
from models import db, User
from flask_login import login_user, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

user_blueprint = Blueprint('user_api_routes', __name__, url_prefix='/api/user')


def create_response(message, result=None, status=200):
    response = {'message': message}
    if result is not None:
        response['result'] = result
    return make_response(jsonify(response), status)


@user_blueprint.route('/welcome', methods=['GET'])
def welcome_all_users():
    return create_response('Welcome User service')

@user_blueprint.route('/all', methods=['GET'])
def get_all_users():
    all_users = User.query.all()
    result = [user.serialize() for user in all_users]
    return create_response('Returning all users', result)


@user_blueprint.route('/create', methods=['POST'])
def create_user():
    try:
        username = request.form["username"]
        password = generate_password_hash(request.form['password'], method='scrypt')

        user = User(username=username, password=password, is_admin=False)
        db.session.add(user)
        db.session.commit()

        return create_response('User Created', user.serialize(), 201)
    except Exception as e:
        print(str(e))
        return create_response('Error in creating user', status=500)


@user_blueprint.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        user.update_api_key()
        db.session.commit()
        login_user(user)
        response = {'message': "Logged in user", 'api_key': user.api_key}
        return make_response(jsonify(response), 200)

    return create_response('Access denied', status=401)


@user_blueprint.route('/logout', methods=['POST'])
def logout():
    if current_user.is_authenticated:
        logout_user()
        return create_response('Logged out')
    return create_response('No user logged in', status=401)


@user_blueprint.route('/<username>/exists', methods=['GET'])
def user_exists(username):
    user = User.query.filter_by(username=username).first()
    return create_response('User exists', {'result': bool(user)}, status=200 if user else 404)


@user_blueprint.route('/', methods=['GET'])
def get_current_user():
    if current_user.is_authenticated:
        return create_response('Current user', current_user.serialize())
    return create_response('User not logged in', status=401)
