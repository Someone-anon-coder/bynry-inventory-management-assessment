import datetime
from flask import Blueprint, jsonify
from sqlalchemy import text
from src.app import db

alerts_bp = Blueprint('alerts', __name__)

@alerts_bp.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    # Step 1: Validate company_id
    company_query = text("SELECT id FROM companies WHERE id = :company_id")
    company = db.session.execute(company_query, {'company_id': company_id}).fetchone()
    if not company:
        return jsonify({"error": "Company not found"}), 404

    # Step 2: Main query to get low-stock products
    query = text("""
        SELECT
            p.id AS product_id,
            p.name AS product_name,
            p.sku,
            i.current_stock,
            p.low_stock_threshold,
            w.id AS warehouse_id,
            w.name AS warehouse_name,
            s.id AS supplier_id,
            s.name AS supplier_name,
            s.contact_email AS supplier_contact
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        JOIN warehouses w ON i.warehouse_id = w.id
        LEFT JOIN suppliers s ON p.supplier_id = s.id
        WHERE w.company_id = :company_id AND i.current_stock <= p.low_stock_threshold
    """)
    
    low_stock_products = db.session.execute(query, {'company_id': company_id}).fetchall()

    alerts = []
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    for product in low_stock_products:
        # Step 3: Check for recent sales activity
        sales_query = text("""
            SELECT SUM(quantity_change) AS total_sold
            FROM inventory_logs
            WHERE product_id = :product_id AND quantity_change < 0 AND created_at >= :start_date
        """)
        sales_result = db.session.execute(sales_query, {'product_id': product.product_id, 'start_date': thirty_days_ago}).fetchone()
        
        total_sold = (sales_result.total_sold * -1) if sales_result and sales_result.total_sold else 0

        if total_sold > 0:
            # Step 4: Calculate days_until_stockout
            avg_daily_sales = total_sold / 30.0
            days_until_stockout = int(product.current_stock / avg_daily_sales) if avg_daily_sales > 0 else None

            alert = {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "sku": product.sku,
                "current_stock": product.current_stock,
                "warehouse_id": product.warehouse_id,
                "warehouse_name": product.warehouse_name,
                "days_until_stockout": days_until_stockout,
                "supplier": None
            }

            if product.supplier_id:
                alert["supplier"] = {
                    "supplier_id": product.supplier_id,
                    "name": product.supplier_name,
                    "contact_email": product.supplier_contact
                }
            
            alerts.append(alert)

    # Step 5: Format final response
    response = {
        "company_id": company_id,
        "alerts": alerts,
        "total_alerts": len(alerts)
    }

    return jsonify(response), 200
