import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

# --- Boilerplate Setup ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Corrected Models ---
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # SKU must be unique. This is enforced at the database level.
    sku = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    # The flawed warehouse_id has been removed.

    def to_dict(self):
        return {
            'id': self.id,
            'sku': self.sku,
            'name': self.name,
            'description': self.description
        }

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Establishes a many-to-one relationship from Inventory to Product.
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, nullable=False)
    stock_level = db.Column(db.Integer, nullable=False, default=0)

    # Relationship to easily access the product from an inventory record.
    product = db.relationship('Product', backref=db.backref('inventories', lazy=True))


# --- Refactored API Endpoint ---
@app.route('/')
def home():
    return '<h1>Welcome to the Bynry Inventory Management API</h1>', 200

@app.route('/product', methods=['POST'])
def create_product():
    """
    Creates a new product and its initial inventory in a single atomic transaction.
    """
    data = request.get_json()

    # 1. Robust Input Validation
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    required_fields = ['sku', 'name', 'warehouse_id', 'stock_level']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    sku = data.get('sku')
    name = data.get('name')
    warehouse_id = data.get('warehouse_id')
    stock_level = data.get('stock_level')
    description = data.get('description') # Optional

    if not isinstance(stock_level, int) or stock_level < 0:
        return jsonify({"error": "Field 'stock_level' must be a non-negative integer."}), 400
    if not isinstance(warehouse_id, int):
         return jsonify({"error": "Field 'warehouse_id' must be an integer."}), 400

    # 2. Idempotency & Uniqueness Check
    if Product.query.filter_by(sku=sku).first():
        return jsonify({"error": f"Product with SKU '{sku}' already exists."}), 409

    try:
        # 3. Atomic Transaction
        # The Product is created without a warehouse_id, correcting the data model.
        new_product = Product(
            sku=sku,
            name=name,
            description=description
        )
        db.session.add(new_product)

        # Flush the session to get the new_product.id before committing.
        # This is safe because it's part of the same transaction.
        db.session.flush()

        initial_inventory = Inventory(
            product_id=new_product.id,
            warehouse_id=warehouse_id,
            stock_level=stock_level
        )
        db.session.add(initial_inventory)

        db.session.commit()

        # 4. Proper API Response
        return jsonify({
            "message": "Product created successfully.",
            "product": new_product.to_dict()
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        # This can happen in a race condition if another request creates the same SKU
        # between our check and our commit.
        return jsonify({"error": "Database integrity error. A product with this SKU may have just been created."}), 409
    except Exception as e:
        db.session.rollback()
        # Log the exception e in a real application
        return jsonify({"error": "An unexpected error occurred."}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
