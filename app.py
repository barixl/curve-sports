from flask import Flask
from extensions import db, login_manager, mail, oauth
from config import Config
from seed_data import seed_data, seed_gym_accessories, cleanup_gym_duplicates, migrate_performance_nutrition
import os
import cloudinary
from sqlalchemy import text

def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    # Tell browsers to cache static files for 1 year (fonts, CSS, JS don't change)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31_536_000
    app.config.from_object(Config)

    # Configure Cloudinary
    cloudinary.config(
        cloud_name=app.config['CLOUDINARY_CLOUD_NAME'],
        api_key=app.config['CLOUDINARY_API_KEY'],
        api_secret=app.config['CLOUDINARY_API_SECRET'],
        secure=True
    )
    if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
        # Only move to /tmp if using the default local SQLite on Vercel
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/curvesports.db'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'images', 'products')

    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except OSError:
        # Ignore on read-only filesystems like Vercel
        pass

    # Bind extensions to this app instance
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    mail.init_app(app)
    oauth.init_app(app)

    # Register Google OAuth — static endpoints avoid a blocking HTTP fetch on startup
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        api_base_url='https://www.googleapis.com/oauth2/v2/',
        jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    # Register blueprints
    from routes.auth import auth_bp
    from routes.shop import shop_bp
    from routes.admin import admin_bp
    from routes.cart import cart_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(cart_bp)

    # All DB work must happen inside the app context
    with app.app_context():
        db.create_all()
        seed_data()
        migrate_performance_nutrition()
        seed_gym_accessories()
        cleanup_gym_duplicates()
        # Add new Order columns if they don't exist yet (safe on re-run)
        new_cols = [
            ('razorpay_order_id',   'VARCHAR(100)'),
            ('razorpay_payment_id', 'VARCHAR(100)'),
        ]
        with db.engine.connect() as conn:
            for col, col_type in new_cols:
                try:
                    conn.execute(text(f'ALTER TABLE orders ADD COLUMN {col} {col_type}'))
                    conn.commit()
                except Exception:
                    conn.rollback()

    # Jinja2 context processors & filters
    from context import register_context
    register_context(app)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, use_reloader=True, reloader_type='watchdog')
