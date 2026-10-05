from flask import Flask
from extensions import db, login_manager, mail, oauth
from config import Config
from seed_data import (seed_data, seed_gym_accessories, cleanup_gym_duplicates,
                       migrate_performance_nutrition, group_categories_for_nav)
import os
import cloudinary
from sqlalchemy import text
from flask_compress import Compress

compress = Compress()

def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    # Tell browsers to cache static files for 1 year (fonts, CSS, JS don't change)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31_536_000
    app.config['COMPRESS_ALGORITHM'] = ['br', 'gzip', 'deflate']
    app.config.from_object(Config)

    # Initialize compression
    compress.init_app(app)

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

    # Database initialization and migrations
    # On Vercel, we avoid running this on every cold start if SKIP_DB_INIT is set
    if not os.environ.get('SKIP_DB_INIT'):
        with app.app_context():
            try:
                db.create_all()

                # Add new columns if they don't exist yet (before the seeds, which query these tables)
                new_cols = [
                    ('orders',             'razorpay_order_id',   'VARCHAR(100)'),
                    ('orders',             'razorpay_payment_id', 'VARCHAR(100)'),
                    ('products',           'option_label',        "VARCHAR(50) DEFAULT 'Pack'"),
                    ('product_variations', 'name',                'VARCHAR(100)'),
                    ('product_variations', 'original_price',      'FLOAT'),
                    ('product_variations', 'badge',               'VARCHAR(30)'),
                    ('order_items',        'variation_name',      'VARCHAR(100)'),
                ]
                for table, col, col_type in new_cols:
                    try:
                        db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        continue
                    if (table, col) == ('product_variations', 'original_price'):
                        # Packs had no MRP of their own until now: the primary pack takes the product's
                        db.session.execute(text(
                            'UPDATE product_variations SET original_price = '
                            '(SELECT original_price FROM products WHERE products.id = product_variations.product_id) '
                            'WHERE is_primary'))
                        db.session.commit()

                seed_data()
                migrate_performance_nutrition()
                seed_gym_accessories()
                cleanup_gym_duplicates()
                group_categories_for_nav()
            except Exception as e:
                print(f"⚠️ Database initialization skipped or failed: {e}")
                db.session.rollback()

    # Jinja2 context processors & filters
    from context import register_context
    register_context(app)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, use_reloader=True, reloader_type='watchdog')
