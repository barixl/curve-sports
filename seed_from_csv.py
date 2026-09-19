"""
Local dev helper: build a real catalogue from products.csv.

The repo ships products.csv (449 products with image URLs) but no importer, and the
real product/category images live in the production Cloudinary account. This script
imports the CSV into the local database and downloads each image into
static/images/{products,categories} (both gitignored), so a fresh local setup has a
populated shop instead of empty placeholders.

Idempotent: re-running updates existing rows (matched on slug) and skips images
already downloaded.

    python seed_from_csv.py
"""
import csv
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from slugify import slugify

from app import create_app
from extensions import db
from models import Brand, Category, Product

CSV_FILE = 'products.csv'
STOCK_DEFAULT = 50
WORKERS = 12

# CSV category name -> slug of a category that already exists in the DB, so the CSV
# products land in the seeded categories instead of creating near-duplicates.
SLUG_ALIASES = {
    'whey-proteins': 'whey-protein',
    'mass-weight-gainers': 'mass-weight-gainer',
}

session = requests.Session()
session.headers['User-Agent'] = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36'
)


def download(url, dest):
    """Fetch url to dest unless it is already there. Returns the filename or None."""
    if not url:
        return None
    if os.path.exists(dest):
        return os.path.basename(dest)
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as fh:
            fh.write(r.content)
        return os.path.basename(dest)
    except Exception as exc:
        print('  ! {} -> {}'.format(url[:70], exc))
        return None


def ext_of(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in ('.webp', '.jpg', '.jpeg', '.png') else '.jpg'


def num(value, default=0.0):
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return default


def main():
    app = create_app()
    with app.app_context():
        products_dir = os.path.join(app.static_folder, 'images', 'products')
        categories_dir = os.path.join(app.static_folder, 'images', 'categories')
        os.makedirs(products_dir, exist_ok=True)
        os.makedirs(categories_dir, exist_ok=True)

        with open(CSV_FILE, encoding='utf-8-sig') as fh:
            rows = list(csv.DictReader(fh))
        print('{} rows in {}'.format(len(rows), CSV_FILE))

        # Categories and brands
        cats, brands = {}, {}
        for row in rows:
            cname = row['Category'].strip()
            if cname and cname not in cats:
                slug = SLUG_ALIASES.get(slugify(cname), slugify(cname))
                cat = Category.query.filter_by(slug=slug).first()
                if not cat:
                    cat = Category(name=cname, slug=slug,
                                   description='{} from trusted brands'.format(cname))
                    db.session.add(cat)
                cat.is_active = True
                cats[cname] = cat

            bname = row['Brand'].strip()
            if bname and bname not in brands:
                bslug = slugify(bname)
                brand = Brand.query.filter_by(slug=bslug).first()
                if not brand:
                    brand = Brand(name=bname, slug=bslug)
                    db.session.add(brand)
                brand.is_active = True
                brands[bname] = brand
        db.session.flush()
        print('{} categories, {} brands'.format(len(cats), len(brands)))

        # Download images
        jobs = []
        for row in rows:
            url = row['Image URL 1'].strip()
            if not url:
                continue
            slug = slugify(row['Product Name'])[:80]
            jobs.append((row, slug, url, os.path.join(products_dir, slug + ext_of(url))))

        print('downloading {} images into static/images/products ...'.format(len(jobs)))
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            files = list(pool.map(lambda j: download(j[2], j[3]), jobs))
        print('{}/{} images available'.format(sum(1 for f in files if f), len(jobs)))

        # Products
        created = updated = 0
        for (row, slug, _url, _path), filename in zip(jobs, files):
            price = num(row['Price (Rs)'])
            mrp = num(row['MRP (Rs)'])
            if price <= 0:
                continue
            bits = ' '.join(x for x in (row.get('Variant/Size', ''),
                                        row.get('Flavour', '')) if x.strip())
            description = (row.get('Description', '').strip()
                           or row.get('Key Benefits', '').strip()
                           or '{} {}'.format(row['Product Name'], bits).strip())

            p = Product.query.filter_by(slug=slug).first()
            if p:
                updated += 1
            else:
                p = Product(slug=slug)
                db.session.add(p)
                created += 1
            p.name = row['Product Name'].strip()
            p.description = description
            p.price = price
            p.original_price = mrp if mrp > price else None
            p.stock = STOCK_DEFAULT
            p.rating = num(row['Rating'])
            p.review_count = int(num(row['No. of Reviews']))
            p.category_id = cats[row['Category'].strip()].id if row['Category'].strip() else None
            p.brand_id = brands[row['Brand'].strip()].id if row['Brand'].strip() else None
            p.is_active = True
            p.product_type = 'simple'
            if filename:
                p.image = filename
        db.session.flush()
        print('products: {} created, {} updated'.format(created, updated))

        # Category thumbnails reuse one product image per category
        thumbs = 0
        for cat in cats.values():
            first = Product.query.filter_by(category_id=cat.id).filter(
                Product.image.isnot(None)).order_by(Product.rating.desc()).first()
            if not first:
                continue
            src = os.path.join(products_dir, first.image)
            if not os.path.exists(src):
                continue
            dest_name = cat.slug + os.path.splitext(first.image)[1]
            shutil.copyfile(src, os.path.join(categories_dir, dest_name))
            cat.image = dest_name
            thumbs += 1
        print('category thumbnails: {}'.format(thumbs))

        # Seeded categories still pointing at demo files that were never committed
        # (e.g. the Sports Nutrition children): reuse the image of the category with
        # the same name, else clear it so the template falls back to its icon.
        def local_image_exists(name):
            return bool(name) and not str(name).startswith('http') and \
                os.path.exists(os.path.join(categories_dir, name))

        good_by_name = {}
        for cat in Category.query.all():
            if local_image_exists(cat.image):
                good_by_name.setdefault(cat.name.strip().lower(), cat.image)

        reused = cleared = 0
        for cat in Category.query.all():
            if not cat.image or str(cat.image).startswith('http') or local_image_exists(cat.image):
                continue
            twin = good_by_name.get(cat.name.strip().lower())
            if twin:
                cat.image = twin
                reused += 1
            else:
                cat.image = None
                cleared += 1
        print('categories repaired: {} reused, {} cleared'.format(reused, cleared))

        # Homepage carousels: flag the best-rated products
        Product.query.update({Product.featured: False, Product.bestseller: False})
        ranked = Product.query.filter(
            Product.image.isnot(None), Product.is_active == True
        ).order_by((Product.rating * Product.review_count).desc()).limit(16).all()
        for i, p in enumerate(ranked):
            p.featured = i < 8
            p.bestseller = i >= 8
        print('flagged {} products for the homepage carousels'.format(len(ranked)))

        # Retire the demo products, whose images were never committed
        demo = Product.query.filter(Product.image.in_(
            ['Whey-Chocolate.webp', 'muscleblaze.webp', 'whey.webp'])).all()
        for p in demo:
            p.is_active = False
        print('deactivated {} demo products'.format(len(demo)))

        db.session.commit()
        print('done')


if __name__ == '__main__':
    main()
