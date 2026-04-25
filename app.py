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

    # Clear old categories to avoid mess during development update
    # In production, we'd use a migration or careful update
    Category.query.delete()
    
    # 1. Performance Nutrition
    perf = Category(name='Performance Nutrition', slug='performance-nutrition', description='Supplements for athletic performance')
    db.session.add(perf)
    db.session.flush()
    
    perf_subs = [
        ('Whey Protein', 'whey-protein'),
        ('Pea & Plant Protein', 'plant-protein'),
        ('Yeast Protein', 'yeast-protein'),
        ('Creatine', 'creatine'),
        ('Pre Workout', 'pre-workout'),
        ('Mass & Weight Gainer', 'mass-gainer'),
        ('L Carnitine', 'l-carnitine'),
        ('BCAA', 'bcaa')
    ]
    for name, slug in perf_subs:
        db.session.add(Category(name=name, slug=slug, parent_id=perf.id))

    # 2. Vitamins
    vit = Category(name='Vitamins', slug='vitamins', description='Essential vitamins and minerals')
    db.session.add(vit)
    db.session.flush()
    
    vit_subs = [
        ('Fish Oil', 'fish-oil'),
        ('Multivitamins', 'multivitamins'),
        ('Magnesium', 'magnesium'),
        ('Single Vitamins', 'single-vitamins'),
        ('Shilajit', 'shilajit'),
        ('Collagen', 'collagen'),
        ('Ashwagandha', 'ashwagandha'),
        ('Pre & Probiotics', 'probiotics')
    ]
    for name, slug in vit_subs:
        db.session.add(Category(name=name, slug=slug, parent_id=vit.id))

    # 3. Health Food
    health = Category(name='Health Food', slug='health-food', description='Healthy snacks and ingredients')
    db.session.add(health)
    db.session.flush()
    
    health_subs = [
        ('Protein Oats', 'protein-oats'),
        ('Peanut Butter', 'peanut-butter'),
        ('Apple Cider Vinegar (ACV)', 'acv'),
        ('Protein Bars', 'protein-bars')
    ]
    for name, slug in health_subs:
        db.session.add(Category(name=name, slug=slug, parent_id=health.id))

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
    products = [
        Product(
            name='Curve Gold 100% Whey Protein', slug='curve-gold-whey-protein',
            description='Premium whey protein concentrate with 24g protein per serving. Ideal for muscle building and recovery.',
            price=1999, original_price=2999, stock=150, category_id=1, brand_id=1,
            rating=4.5, review_count=2341, featured=True, bestseller=True,
            image=product_images[0]
        ),
        Product(
            name='ON Gold Standard 100% Whey', slug='on-gold-standard-whey',
            description="World's best selling whey protein. 24g blended protein, 5.5g BCAAs per serving.",
            price=4299, original_price=5499, stock=80, category_id=1, brand_id=2,
            rating=4.8, review_count=8921, featured=True, bestseller=True,
            image=product_images[1]
        ),
        Product(
            name='MuscleBlaze Biozyme Whey', slug='muscleblaze-biozyme-whey',
            description='Enhanced absorption whey protein with protease enzyme blend.',
            price=2799, original_price=3599, stock=200, category_id=1, brand_id=3,
            rating=4.4, review_count=5612, featured=True,
            image=product_images[2]
        ),
        Product(
            name='Curve Pure Creatine Monohydrate', slug='curve-creatine-mono',
            description='100% pure micronized creatine monohydrate. 3g per serving for strength and power.',
            price=499, original_price=799, stock=300, category_id=2, brand_id=1,
            rating=4.6, review_count=3210, bestseller=True,
            image=product_images[0]
        ),
        Product(
            name='MyProtein Impact Whey', slug='myprotein-impact-whey',
            description="Europe's best selling protein powder with 21g protein per serving.",
            price=2199, original_price=2999, stock=120, category_id=1, brand_id=4,
            rating=4.3, review_count=4100,
            image=product_images[1]
        ),
        Product(
            name='Curve Pre-Workout Ignite', slug='curve-preworkout-ignite',
            description='Explosive pre-workout formula with caffeine, beta-alanine and citrulline.',
            price=999, original_price=1499, stock=90, category_id=3, brand_id=1,
            rating=4.2, review_count=1890, featured=True,
            image=product_images[2]
        ),
        Product(
            name='AS-IT-IS Whey Protein Concentrate', slug='as-it-is-whey',
            description='Pure, unadulterated whey protein concentrate 80%. No additives, no fillers.',
            price=1599, original_price=2199, stock=250, category_id=1, brand_id=6,
            rating=4.5, review_count=7823, bestseller=True,
            image=product_images[0]
        ),
        Product(
            name='MuscleBlaze Mass Gainer XXL', slug='muscleblaze-mass-gainer-xxl',
            description='60g protein and 1000+ calories per serving for extreme mass gain.',
            price=1799, original_price=2399, stock=60, category_id=4, brand_id=3,
            rating=4.1, review_count=3456,
            image=product_images[1]
        ),
        Product(
            name='Curve Wellness BCAA 2:1:1', slug='curve-bcaa',
            description='Pure BCAA in 2:1:1 ratio for muscle recovery and endurance.',
            price=799, original_price=1199, stock=180, category_id=6, brand_id=1,
            rating=4.3, review_count=1230,
            image=product_images[2]
        ),
        Product(
            name='ON Opti-Men Multivitamin', slug='on-opti-men-multivitamin',
            description='Complete multivitamin for active men with 75+ ingredients.',
            price=1899, original_price=2499, stock=100, category_id=5, brand_id=2,
            rating=4.7, review_count=4532, featured=True,
            image=product_images[0]
        ),
    ]
    for p in products:
        db.session.add(p)

    db.session.commit()
    print('✅ Demo data seeded.')


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
