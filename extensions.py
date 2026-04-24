"""
extensions.py
─────────────
Flask extension objects are created here (without being bound to any app).
Both app.py and models.py import from this module, which breaks the
circular-import chain that caused the 'SQLAlchemy not registered' error.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
oauth = OAuth()
