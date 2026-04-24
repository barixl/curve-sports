from app import create_app
from extensions import db
from models import Product
import os

def update_images():
    app = create_app()
    with app.app_context():
        # List of available images
        product_images = ['Whey-Chocolate.jpg', 'muscleblaze.jpg', 'whey.webp']
        
        products = Product.query.all()
        if not products:
            print("No products found in database.")
            return

        print(f"Updating {len(products)} products...")
        
        for i, p in enumerate(products):
            # Assign images repetitively
            p.image = product_images[i % len(product_images)]
            print(f"Updated {p.name} -> {p.image}")
            
        db.session.commit()
        print("✅ All products updated with repetitive images!")

if __name__ == '__main__':
    update_images()
