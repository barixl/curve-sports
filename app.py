from flask import Flask
from extensions import db, login_manager, mail, oauth   # ← single source of truth
import os


def create_app():
    app = Flask(__name__, static_folder='static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'curvesports-secret-key-change-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///curvesports.db'
    if os.environ.get('VERCEL'):
        # Move DB to /tmp for Vercel as the rest of the FS is read-only
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/curvesports.db'
        
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'images', 'products')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # Google OAuth Config
    app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID')
    app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', 'YOUR_GOOGLE_CLIENT_SECRET')

    # Mail Config (using a common setup, user should update these)
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your-email@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your-app-password')
    app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

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

    # Register Google OAuth
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
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
        _seed_data()

    # Jinja2 context processors & filters
    from context import register_context
    register_context(app)

    return app


def _seed_data():
    """Populate the DB with demo data on first run (idempotent)."""
    from models import User, Category, Brand, Product
    from werkzeug.security import generate_password_hash

    if User.query.filter_by(email='admin@curvesports.com').first():
        return  # already seeded

    # Admin user
    admin = User(
        name='Admin User',
        email='admin@curvesports.com',
        password=generate_password_hash('admin123'),
        is_admin=True,
        email_verified=True,
        phone='9999999999',
    )
    db.session.add(admin)

    # Categories (Parent & Child)
    # ── PROTEIN ──────────────────────────────────────────
    prot = Category(name='PROTEIN', slug='protein', description='High quality protein supplements')
    db.session.add(prot)
    db.session.flush()
    
    cat_whey = Category(name='Whey Protein', slug='whey-protein', parent_id=prot.id)
    cat_iso  = Category(name='Whey Protein Isolate', slug='whey-isolate', parent_id=prot.id)
    cat_cas  = Category(name='Casein Protein', slug='casein-protein', parent_id=prot.id)
    cat_plant = Category(name='Plant Protein', slug='plant-protein', parent_id=prot.id)
    
    # ── GAINERS ──────────────────────────────────────────
    gain = Category(name='GAINERS', slug='gainers')
    db.session.add(gain)
    db.session.flush()
    
    cat_mass = Category(name='Mass Gainer', slug='mass-gainer', parent_id=gain.id)
    cat_weight = Category(name='Weight Gainer', slug='weight-gainer', parent_id=gain.id)
    
    # ── PRE/POST WORKOUT ──────────────────────────────────
    pre_post = Category(name='PRE/POST WORKOUT', slug='workout')
    db.session.add(pre_post)
    db.session.flush()
    
    cat_pre = Category(name='Pre Workout', slug='pre-workout', parent_id=pre_post.id)
    cat_bcaa = Category(name='BCAA', slug='bcaa', parent_id=pre_post.id)
    cat_crea = Category(name='Creatine', slug='creatine', parent_id=pre_post.id)
    cat_glut = Category(name='Glutamine', slug='glutamine', parent_id=pre_post.id)
    
    # ── WELLNESS ─────────────────────────────────────────
    well = Category(name='WELLNESS', slug='wellness')
    db.session.add(well)
    db.session.flush()
    
    cat_multi = Category(name='Multivitamins', slug='multivitamins', parent_id=well.id)
    cat_fish = Category(name='Fish Oil', slug='fish-oil', parent_id=well.id)
    cat_biotin = Category(name='Biotin', slug='biotin', parent_id=well.id)
    cat_zma = Category(name='ZMA', slug='zma', parent_id=well.id)
    
    all_cats = [cat_whey, cat_iso, cat_cas, cat_plant, cat_mass, cat_weight, 
                cat_pre, cat_bcaa, cat_crea, cat_glut, cat_multi, cat_fish, cat_biotin, cat_zma]
    for c in all_cats:
        db.session.add(c)

    # Brands
    brands = [
        Brand(name='Curve Gold',      slug='curve-gold',     description='Premium in-house brand'),
        Brand(name='Optimum Nutrition',  slug='optimum-nutrition', description='World leading supplement brand'),
        Brand(name='MuscleBlaze',        slug='muscleblaze',       description="India's top sports nutrition brand"),
        Brand(name='MyProtein',          slug='myprotein',         description="Europe's largest sports nutrition brand"),
        Brand(name='HealthKart',         slug='healthkart',        description='Trusted Indian health brand'),
        Brand(name='AS-IT-IS Nutrition', slug='as-it-is',          description='Pure & unadulterated supplements'),
    ]
    for b in brands:
        db.session.add(b)

    db.session.flush()  # assign IDs so foreign keys work below

    # Products
    product_images = ['Whey-Chocolate.jpg', 'muscleblaze.jpg', 'whey.webp']
    
    # Helper to add 4 products for each category
    def add_demo_products(cat_id, base_name, base_slug, brand_id):
        for i in range(1, 5):
            p = Product(
                name=f"{base_name} Pro {i}",
                slug=f"{base_slug}-{i}",
                description=f"Premium {base_name} formula for maximum results. Pure and authentic.",
                price=1000 + (i*200),
                original_price=1500 + (i*200),
                stock=50 + (i*10),
                category_id=cat_id,
                brand_id=brand_id,
                rating=4.0 + (i*0.2),
                review_count=100 * i,
                image=product_images[i % 3]
            )
            db.session.add(p)

    # Adding products for some key sub-categories
    add_demo_products(cat_whey.id, 'Curve Whey', 'curve-whey', 1)
    add_demo_products(cat_iso.id, 'ON Isolate', 'on-isolate', 2)
    add_demo_products(cat_mass.id, 'MB Mass', 'mb-mass', 3)
    add_demo_products(cat_pre.id, 'Curve Ignite', 'curve-ignite', 1)
    add_demo_products(cat_multi.id, 'Opti-Men', 'opti-men', 2)
    add_demo_products(cat_crea.id, 'Curve Creatine', 'curve-creatine', 1)
    add_demo_products(cat_bcaa.id, 'BCAA Recovery', 'bcaa-recovery', 1)
    add_demo_products(cat_fish.id, 'Fish Oil Premium', 'fish-oil', 5)

    db.session.commit()

    db.session.commit()
    print('✅ Demo data seeded.')


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
