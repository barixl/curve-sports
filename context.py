import json
from models import Category


def register_context(app):
    @app.context_processor
    def inject_globals():
        cats = Category.query.filter_by(is_active=True).all()
        return dict(categories_nav=cats)

    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value)
        except Exception:
            return {}
