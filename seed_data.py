from extensions import db
from models import User, Category, Brand, Product
from werkzeug.security import generate_password_hash


def seed_data():
    """Populate the DB with demo data on first run (idempotent)."""
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

    # Main Categories
    cats = [
        Category(name='Whey Protein',  slug='whey-protein',  description='High quality whey protein supplements'),
        Category(name='Creatine',      slug='creatine',      description='Pure creatine monohydrate'),
        Category(name='Pre Workout',   slug='pre-workout',   description='Energy & focus pre-workout'),
        Category(name='Mass Gainer',   slug='mass-gainer',   description='Weight & mass gainer supplements'),
        Category(name='Multivitamins', slug='multivitamins', description='Daily vitamins & minerals'),
        Category(name='BCAA',          slug='bcaa',          description='Branched Chain Amino Acids'),
        Category(name='Fat Burner',    slug='fat-burner',    description='Weight loss & fat burning'),
        Category(name='Protein Bars',  slug='protein-bars',  description='On the go protein snacks'),
    ]
    for c in cats:
        db.session.add(c)
    db.session.flush()

    # Performance Nutrition Hierarchy
    perf_nut = Category(name='Performance Nutrition', slug='performance-nutrition', description='Supplements for elite performance')
    db.session.add(perf_nut)
    db.session.flush()

    sub_cats = [
        Category(name='Whey Protein', slug='perf-whey-protein', parent_id=perf_nut.id, image='whey-protein.png'),
        Category(name='Pea & Plant Protein', slug='pea-plant-protein', parent_id=perf_nut.id, image='pea-plant-protein.png'),
        Category(name='Yeast Protein', slug='yeast-protein', parent_id=perf_nut.id, image='yeast-protein.png'),
        Category(name='Creatine', slug='perf-creatine', parent_id=perf_nut.id, image='creatine.png'),
        Category(name='Pre Workout', slug='perf-pre-workout', parent_id=perf_nut.id, image='pre-workout.png'),
        Category(name='Mass & Weight Gainer', slug='mass-weight-gainer', parent_id=perf_nut.id, image='mass-gainer.png'),
        Category(name='L Carnitine', slug='l-carnitine', parent_id=perf_nut.id, image='l-carnitine.png'),
        Category(name='BCAA', slug='perf-bcaa', parent_id=perf_nut.id, image='bcaa.png'),
    ]
    for sc in sub_cats:
        db.session.add(sc)

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
