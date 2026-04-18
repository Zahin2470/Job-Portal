import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()  # Load from .env file

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-secret")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback-jwt-key")
    
<<<<<<< HEAD
    



=======
>>>>>>> a0174eb1882d98f6fb0670cc5f8547e5b6cbe316
# This will load your .env file and configure the database.

