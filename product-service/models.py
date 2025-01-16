from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_app(app):
    db.app = app
    db.init_app(app)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    price = db.Column(db.Integer, nullable=True)
    image = db.Column(db.String(255))
    version = db.Column(db.Integer, nullable=False, default=0)

    def __init__(self, name, slug, price=None, image=None, version=0):
        self.name = name
        self.slug = slug
        self.price = price
        self.image = image
        self.version = version

    def __repr__(self):
        return f'<product {self.id} {self.name}>'

    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'price': self.price,
            'image': self.image,
            'version': self.version
        }
