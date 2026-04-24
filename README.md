# Curve Sports — Flask E-Commerce Store

A full-featured e-commerce web application inspired by curvesports.com, built with Flask.

---

## 🚀 Features

### 🛍️ Storefront
- **Homepage** — Hero banner, category grid, featured/bestseller/new-arrival product carousels, promo section
- **Product Listing** — Filter by category, brand, price range; sort by popularity, price, newest, rating; pagination
- **Product Detail** — Image display, ratings, reviews, add to cart, wishlist, related products
- **Search** — Full-text product search
- **Shopping Cart** — Add/remove/update quantities, coupon code application, delivery charge logic
- **Checkout** — Address selection/creation, multiple payment method options (COD, UPI, Card, Net Banking)
- **Order Success** — Confirmation page with order number
- **Wishlist** — Save products for later
- **User Auth** — Register, login, logout, remember me
- **Profile** — Edit profile, change password, manage addresses, view order history

### 🔧 Admin Dashboard (`/admin`)
| Section | Features |
|---------|----------|
| **Dashboard** | Revenue stats, today's metrics, revenue chart (6 months), order status donut, top products, low-stock alerts, recent orders |
| **Products** | List, search, filter, add, edit, delete/deactivate, image upload, featured/bestseller flags |
| **Categories** | CRUD with icon emoji, image upload, active toggle |
| **Brands** | CRUD with logo upload, active toggle |
| **Orders** | List with status/search filters, detail view, status update workflow |
| **Users** | List, search, activate/deactivate |
| **Coupons** | Create percent/flat coupons, expiry dates, usage limits, min order amounts |
| **Banners** | Homepage banner management with image upload and position ordering |
| **Reviews** | View and delete customer reviews |
| **Analytics** | Monthly revenue/orders bar+line chart, revenue by category donut, top products by revenue |
| **Settings** | Store info, shipping settings, payment method toggles |

---

## 📦 Setup

### 1. Create & activate virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the application
```bash
python run.py
```

The app will start at: **http://localhost:5000**

---

## 🔑 Demo Credentials

| Role  | Email                   | Password   |
|-------|-------------------------|------------|
| Admin | admin@curvesports.com      | admin123   |

- **Admin Panel:** http://localhost:5000/admin
- **Register** a new customer account at: http://localhost:5000/register

---

## 🗂️ Project Structure

```
curvesports_clone/
├── app.py              # App factory, DB init, seed data
├── run.py              # Entry point
├── models.py           # SQLAlchemy models
├── context.py          # Jinja context processors & filters
├── requirements.txt
├── routes/
│   ├── auth.py         # Login, register, profile, addresses
│   ├── shop.py         # Homepage, products, product detail, wishlist
│   ├── cart.py         # Cart, checkout, orders
│   └── admin.py        # Full admin panel
├── templates/
│   ├── base.html       # Shop base layout (header, footer, nav)
│   ├── shop/           # All storefront templates
│   ├── auth/           # Login, register, profile
│   └── admin/          # Admin dashboard templates
├── static/
│   ├── css/
│   │   ├── style.css   # Storefront styles
│   │   └── admin.css   # Admin panel styles
│   └── images/         # Uploaded product/category/brand images
└── instance/
    └── curvesports.db     # SQLite database (auto-created)
```

---

## 🛠️ Tech Stack

- **Backend:** Flask 3.0, Flask-SQLAlchemy, Flask-Login
- **Database:** SQLite (easily swappable to PostgreSQL/MySQL)
- **Frontend:** Vanilla HTML/CSS/JS, Chart.js for admin charts
- **Fonts:** Rajdhani (headings) + DM Sans (body) via Google Fonts
- **Icons:** Font Awesome 6

---

## 🔄 Switching to PostgreSQL

In `app.py`, change:
```python
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///curvesports.db'
```
to:
```python
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@localhost/curvesports'
```
Then run `pip install psycopg2-binary`.

---

## 📸 Product Images

By default, products use generated SVG placeholder art. To add real images:
1. Upload images via the Admin → Products → Edit product page
2. Images are stored in `static/images/products/`
