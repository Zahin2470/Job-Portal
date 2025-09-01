"""""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
"""


from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Use DATABASE_URL from Render environment
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/jobhive_db"  # fallback for local dev
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # CORS (allow frontend to call API)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Example route
    @app.route("/api/hello")
    def hello():
        return {"message": "Hello from Flask + Render!"}

    return app

# Create app for Gunicorn
app = create_app()