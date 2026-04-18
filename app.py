from flask import Flask
from extensions import db, login_manager   # ← single source of truth
import os


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nutrabay-secret-key-change-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nutrabay.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'images', 'products')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Bind extensions to this app instance
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

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

    if User.query.filter_by(email='admin@nutrabay.com').first():
        return  # already seeded

    # Admin user
    admin = User(
        name='Admin User',
        email='admin@nutrabay.com',
        password=generate_password_hash('admin123'),
        is_admin=True,
        phone='9999999999',
    )
    db.session.add(admin)

    # Categories
    cats = [
        Category(name='Whey Protein',  slug='whey-protein',  icon='🥛', description='High quality whey protein supplements'),
        Category(name='Creatine',      slug='creatine',      icon='💪', description='Pure creatine monohydrate'),
        Category(name='Pre Workout',   slug='pre-workout',   icon='⚡', description='Energy & focus pre-workout'),
        Category(name='Mass Gainer',   slug='mass-gainer',   icon='📈', description='Weight & mass gainer supplements'),
        Category(name='Multivitamins', slug='multivitamins', icon='💊', description='Daily vitamins & minerals'),
        Category(name='BCAA',          slug='bcaa',          icon='🔬', description='Branched Chain Amino Acids'),
        Category(name='Fat Burner',    slug='fat-burner',    icon='🔥', description='Weight loss & fat burning'),
        Category(name='Protein Bars',  slug='protein-bars',  icon='🍫', description='On the go protein snacks'),
    ]
    for c in cats:
        db.session.add(c)

    # Brands
    brands = [
        Brand(name='Nutrabay Gold',      slug='nutrabay-gold',     description='Premium in-house brand'),
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
    products = [
        Product(
            name='Nutrabay Gold 100% Whey Protein', slug='nutrabay-gold-whey-protein',
            description='Premium whey protein concentrate with 24g protein per serving. Ideal for muscle building and recovery.',
            price=1999, original_price=2999, stock=150, category_id=1, brand_id=1,
            flavor='Chocolate', weight='1kg', rating=4.5, review_count=2341, featured=True, bestseller=True,
        ),
        Product(
            name='ON Gold Standard 100% Whey', slug='on-gold-standard-whey',
            description="World's best selling whey protein. 24g blended protein, 5.5g BCAAs per serving.",
            price=4299, original_price=5499, stock=80, category_id=1, brand_id=2,
            flavor='Double Rich Chocolate', weight='2kg', rating=4.8, review_count=8921, featured=True, bestseller=True,
        ),
        Product(
            name='MuscleBlaze Biozyme Whey', slug='muscleblaze-biozyme-whey',
            description='Enhanced absorption whey protein with protease enzyme blend.',
            price=2799, original_price=3599, stock=200, category_id=1, brand_id=3,
            flavor='Rich Chocolate', weight='1kg', rating=4.4, review_count=5612, featured=True,
        ),
        Product(
            name='Nutrabay Pure Creatine Monohydrate', slug='nutrabay-creatine-mono',
            description='100% pure micronized creatine monohydrate. 3g per serving for strength and power.',
            price=499, original_price=799, stock=300, category_id=2, brand_id=1,
            flavor='Unflavoured', weight='250g', rating=4.6, review_count=3210, bestseller=True,
        ),
        Product(
            name='MyProtein Impact Whey', slug='myprotein-impact-whey',
            description="Europe's best selling protein powder with 21g protein per serving.",
            price=2199, original_price=2999, stock=120, category_id=1, brand_id=4,
            flavor='Vanilla', weight='1kg', rating=4.3, review_count=4100,
        ),
        Product(
            name='Nutrabay Pre-Workout Ignite', slug='nutrabay-preworkout-ignite',
            description='Explosive pre-workout formula with caffeine, beta-alanine and citrulline.',
            price=999, original_price=1499, stock=90, category_id=3, brand_id=1,
            flavor='Watermelon', weight='300g', rating=4.2, review_count=1890, featured=True,
        ),
        Product(
            name='AS-IT-IS Whey Protein Concentrate', slug='as-it-is-whey',
            description='Pure, unadulterated whey protein concentrate 80%. No additives, no fillers.',
            price=1599, original_price=2199, stock=250, category_id=1, brand_id=6,
            flavor='Unflavoured', weight='1kg', rating=4.5, review_count=7823, bestseller=True,
        ),
        Product(
            name='MuscleBlaze Mass Gainer XXL', slug='muscleblaze-mass-gainer-xxl',
            description='60g protein and 1000+ calories per serving for extreme mass gain.',
            price=1799, original_price=2399, stock=60, category_id=4, brand_id=3,
            flavor='Chocolate', weight='3kg', rating=4.1, review_count=3456,
        ),
        Product(
            name='Nutrabay Wellness BCAA 2:1:1', slug='nutrabay-bcaa',
            description='Pure BCAA in 2:1:1 ratio for muscle recovery and endurance.',
            price=799, original_price=1199, stock=180, category_id=6, brand_id=1,
            flavor='Mango', weight='200g', rating=4.3, review_count=1230,
        ),
        Product(
            name='ON Opti-Men Multivitamin', slug='on-opti-men-multivitamin',
            description='Complete multivitamin for active men with 75+ ingredients.',
            price=1899, original_price=2499, stock=100, category_id=5, brand_id=2,
            flavor='N/A', weight='90 tablets', rating=4.7, review_count=4532, featured=True,
        ),
    ]
    for p in products:
        db.session.add(p)

    db.session.commit()
    print('✅ Demo data seeded.')


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
