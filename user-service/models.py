from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash
from datetime import datetime

db = SQLAlchemy()

def init_app(app):
    """Initialize the database with the Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    api_key = db.Column(db.String(255), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    authenticated = db.Column(db.Boolean, default=False)

    def __init__(self, username, password, is_admin=False, api_key=None):
        self.username = username
        self.password = password
        self.is_admin = is_admin
        self.api_key = api_key

    def __repr__(self):
        return f'<User {self.id}, {self.username}>'

    def serialize(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_admin': self.is_admin,
            'api_key': self.api_key,
            'is_active': self.is_active,
        }

    def update_api_key(self):
        self.api_key = generate_password_hash(self.username + str(datetime.utcnow()))
