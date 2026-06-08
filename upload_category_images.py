"""
Script to upload local category images to Cloudinary and update the database.
Maps image filenames to categories by name relevancy.
Run with: python upload_category_images.py
"""

import os
import sys
from app import create_app
from extensions import db
from models import Category
import cloudinary
import cloudinary.uploader

GENERIC_PLACEHOLDER = "gsmkotj5zkrcztkeuhiv"

# Map: category slug -> local image filename (in static/images/categories/)
SLUG_TO_IMAGE = {
    # Categories with null images
    "apple-cider-vinegar": "Apple Cider Vinegar.webp",
    "ashwagandha": "Ashwagandha.webp",
    "bone-joints": "Bone & Joints.webp",
    "digestion": "Digestion.webp",
    "l-carnitine-1": "L-Carnite(1).webp",
    "mass-weight-gainers": "Mass & Weight Gainer.webp",
    "shilajit": "Shilajit.webp",
    "skin-hair": "Skin & Hair.webp",
    "sleep": "Sleep.webp",
    "vitality": "Vitality.webp",
    "weight-loss": "Weight Loss.webp",
    "whey-proteins": "Whey Protein.webp",
    # Subcategories with generic placeholder images
    "fish-oil": "Fish Oil.webp",
    "vitamins-magnesium": "Magnesium.webp",
    "apple-cider-vinegar-acv": "Apple Cider Vinegar.webp",
}


def upload_and_update():
    app = create_app()
    images_dir = os.path.join(app.static_folder, "images", "categories")

    with app.app_context():
        updated = 0
        skipped = 0
        errors = 0

        for slug, filename in SLUG_TO_IMAGE.items():
            category = Category.query.filter_by(slug=slug).first()
            if not category:
                print(f"  [SKIP] No category found with slug: {slug}")
                skipped += 1
                continue

            # Skip if already has a real (non-generic) Cloudinary image
            if category.image and GENERIC_PLACEHOLDER not in category.image:
                print(f"  [SKIP] {category.name} already has a real image")
                skipped += 1
                continue

            image_path = os.path.join(images_dir, filename)
            if not os.path.exists(image_path):
                print(f"  [ERROR] Image file not found: {image_path}")
                errors += 1
                continue

            print(f"  [UPLOAD] {category.name} <- {filename}")
            try:
                result = cloudinary.uploader.upload(
                    image_path,
                    folder="curve-sports/categories",
                    public_id=slug,
                    overwrite=True,
                    resource_type="image",
                )
                url = result.get("secure_url")
                category.image = url
                db.session.commit()
                print(f"    -> {url}")
                updated += 1
            except Exception as e:
                db.session.rollback()
                print(f"  [ERROR] Failed to upload {filename}: {e}")
                errors += 1

        print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    upload_and_update()
