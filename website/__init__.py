from flask import Flask
from flask_socketio import SocketIO
import os

# Initialize SocketIO without app first
socketio = SocketIO()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'Rishikesh kumar is the owner of this project and this project is made with the help of ai and this project is open source and free to use for everyone'

    # Ensure downloads directory exists (Config/Setup)
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    # Register Blueprint
    from .views import views
    app.register_blueprint(views, url_prefix='/')

    # Initialize SocketIO with app
    socketio.init_app(app)

    return app