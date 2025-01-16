from flask import Flask
from routes import order_blueprint
from models import db, init_app
from flask_migrate import Migrate
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(order_blueprint)
init_app(app)
# migrate = Migrate(app, db)

def welcome():
    return "Welcome app-service"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)