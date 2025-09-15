# Part 3: API Implementation

## 1. Assumptions
- **Database Schema**: The implementation assumes the relational schema designed in Part 2 of the case study is in place. This includes tables for `companies`, `warehouses`, `products`, `inventory`, `suppliers`, and `inventory_logs`.
- **Low-Stock Threshold**: The `products` table is assumed to have a `low_stock_threshold` column, which is an integer value. A product's stock is considered low if its `current_stock` is at or below this threshold.
- **Recent Sales Activity**: A product is considered to have recent sales activity if there is at least one record in the `inventory_logs` table for that product with a negative `quantity_change` (indicating a sale) within the last 30 days.
- **Days Until Stockout Calculation**: This is calculated by first determining the average daily sales volume over the past 30 days from the `inventory_logs`. The `current_stock` is then divided by this average. If there is no sales data for the period, this value will be `null`.

## 2. Approach & Logic
The API endpoint will be implemented with the following logic:

1.  **Input Validation**: The `company_id` from the URL will be validated to ensure it corresponds to an existing company. If not, a 404 error is returned.
2.  **Efficient Single Query**: A single, comprehensive SQL query will be executed. This query will:
    -   `JOIN` the `inventory` table with `products`, `warehouses`, and `suppliers`.
    -   Filter the results for the given `company_id`.
    -   Filter for products where the `current_stock` is less than or equal to the `low_stock_threshold`.
    This approach avoids the N+1 query problem by fetching all potentially relevant data in one database call.
3.  **Sales Data Calculation**: For each low-stock product, a separate query will be made to the `inventory_logs` table to calculate the total sales over the last 30 days.
4.  **In-Memory Filtering & Calculation**:
    -   The results from the main query will be filtered in the Python application to only include products with recent sales activity (i.e., sales in the last 30 days).
    -   The `days_until_stockout` will be calculated for each of these products. A division-by-zero error will be handled for products with no sales in the last 30 days by setting the value to `null`.
5.  **JSON Response Formatting**: The final data will be structured into the specified JSON format, including a list of alerts and a `total_alerts` count.
6.  **Return Response**: The formatted JSON will be returned with a 200 OK status. If no alerts are generated, an empty list will be returned.

## 3. Edge Case Handling
The API has been designed to be resilient and provide clear feedback in various scenarios:

-   **Invalid `company_id`**: If a request is made with a `company_id` that does not exist in the `companies` table, the API will return a `404 Not Found` status code. The JSON response body will contain an error message, such as `{"error": "Company not found"}`.

-   **No Alerts Found**: If a valid `company_id` is provided, but there are no products that meet both the low-stock and recent sales activity criteria, the API will return a `200 OK` status. The response body will contain an empty `alerts` array and `total_alerts` will be `0`.

-   **Missing Relational Data (Suppliers)**: The main SQL query uses a `LEFT JOIN` to fetch supplier information. This ensures that all relevant products are included, even if they are not associated with a supplier. In the Python logic, if a product's `supplier_id` is `null`, the corresponding `supplier` object in the JSON response for that alert will also be set to `null`, preventing errors and providing a predictable output.

-   **No Sales History**: The `days_until_stockout` calculation depends on historical sales data. If a product has low stock but has had no sales in the last 30 days, a division-by-zero error is avoided. In this case, the `days_until_stockout` value is set to `null` in the final JSON response.

## 4. Final Implementation
```python
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
```
