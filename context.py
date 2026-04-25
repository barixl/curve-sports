import json
import time
from models import Category, Brand

# Simple in-process cache: holds the navbar data for 60 seconds
_nav_cache = {'data': None, 'expires': 0}
_NAV_TTL = 60  # seconds


def _build_nav():
    cats = Category.query.filter_by(is_active=True, parent_id=None).order_by(Category.name.asc()).all()
    brands = Brand.query.filter_by(is_active=True).order_by(Brand.name.asc()).all()

    grouped_brands = {}
    for b in brands:
        first = b.name[0].upper()
        if first not in grouped_brands:
            grouped_brands[first] = []
        grouped_brands[first].append(b)

    alphabet = sorted(grouped_brands.keys())
    return dict(categories_nav=cats, brands_nav=brands, grouped_brands=grouped_brands, alphabet=alphabet)


def invalidate_nav_cache():
    """Call this after any admin change to brands/categories."""
    _nav_cache['expires'] = 0


def register_context(app):
    @app.context_processor
    def inject_globals():
        now = time.monotonic()
        if _nav_cache['data'] is None or now > _nav_cache['expires']:
            _nav_cache['data'] = _build_nav()
            _nav_cache['expires'] = now + _NAV_TTL
        return _nav_cache['data']

    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value)
        except Exception:
            return {}

    @app.template_filter('img_url')
    def img_url_filter(path, folder=''):
        """Return the correct image URL whether path is a full URL or a local filename."""
        if not path:
            return ''
        path = path.strip()
        if path.startswith('http://') or path.startswith('https://') or path.startswith('//'):
            return path
        from flask import url_for
        return url_for('static', filename=f'images/{folder}/{path}')
