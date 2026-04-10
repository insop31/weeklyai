import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False


BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = BASE_DIR / ".env"


def load_environment():
    return load_dotenv(dotenv_path=DOTENV_PATH, override=False)


load_environment()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "fallback-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
