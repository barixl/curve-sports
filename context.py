import json
from models import Category, Brand


def register_context(app):
    @app.context_processor
    def inject_globals():
        cats = Category.query.filter_by(is_active=True).all()
        brands = Brand.query.filter_by(is_active=True).order_by(Brand.name.asc()).all()
        
        # Group brands by alphabet
        grouped_brands = {}
        for b in brands:
            first = b.name[0].upper()
            if first not in grouped_brands:
                grouped_brands[first] = []
            grouped_brands[first].append(b)
        
        # Sort keys
        alphabet = sorted(grouped_brands.keys())
        
        return dict(categories_nav=cats, brands_nav=brands, grouped_brands=grouped_brands, alphabet=alphabet)

    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value)
        except Exception:
            return {}
