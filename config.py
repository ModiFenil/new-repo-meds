import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-in-production')
    
    MYSQL_HOST_NAME = os.environ.get('MYSQL_HOST_NAME', 'localhost')
    MYSQL_USER_NAME = os.environ.get('MYSQL_USER_NAME', 'root')
    
    # Handle empty password properly
    _mysql_password = os.environ.get('MYSQL_PASSWORD_NAME', '')
    MYSQL_PASSWORD_NAME = None if _mysql_password == '' else _mysql_password
    
    MYSQL_DB_NAME = os.environ.get('MYSQL_DB_NAME', 'medscred_db')
    
    # Fix the SQLALCHEMY_DATABASE_URI for empty password
    if MYSQL_PASSWORD_NAME is None:
        SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{MYSQL_USER_NAME}@{MYSQL_HOST_NAME}:3306/{MYSQL_DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{MYSQL_USER_NAME}:{MYSQL_PASSWORD_NAME}@{MYSQL_HOST_NAME}:3306/{MYSQL_DB_NAME}"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'connect_args': {
            'connect_timeout': 20,
            'ssl_disabled': True
        }
    }
    
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    MYSQL_DB_NAME = os.environ.get('TEST_DATABASE_URL', 'medscred_test_db')
    
    if Config.MYSQL_PASSWORD_NAME is None:
        SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{Config.MYSQL_USER_NAME}@{Config.MYSQL_HOST_NAME}:3306/{MYSQL_DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{Config.MYSQL_USER_NAME}:{Config.MYSQL_PASSWORD_NAME}@{Config.MYSQL_HOST_NAME}:3306/{MYSQL_DB_NAME}"

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
