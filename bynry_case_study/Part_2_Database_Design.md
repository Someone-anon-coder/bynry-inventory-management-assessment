# Part 2: Database Design

## 1. Database Schema (SQL DDL)
```sql
-- #############################################################################
-- # Table: companies
-- # Description: Stores company records for multi-tenancy. Each company has its
-- # own set of warehouses.
-- #############################################################################
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- #############################################################################
-- # Table: suppliers
-- # Description: Stores supplier information. Products are linked to a supplier.
-- #############################################################################
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    contact_email VARCHAR(255) UNIQUE,
    contact_phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- #############################################################################
-- # Table: warehouses
-- # Description: Stores warehouse information, linked to a specific company.
-- # This enforces the multi-tenant data separation.
-- #############################################################################
CREATE TABLE warehouses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    location TEXT,
    company_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_company
        FOREIGN KEY(company_id)
        REFERENCES companies(id)
        ON DELETE RESTRICT
);

-- #############################################################################
-- # Table: products
-- # Description: Central catalog of all products, including individual items
-- # and bundles. A flag `is_bundle` distinguishes them.
-- #############################################################################
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    supplier_id INTEGER NOT NULL,
    is_bundle BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_supplier
        FOREIGN KEY(supplier_id)
        REFERENCES suppliers(id)
        ON DELETE RESTRICT,

    CONSTRAINT price_non_negative
        CHECK (price >= 0)
);

-- #############################################################################
-- # Table: inventory
-- # Description: Junction table to track the quantity of each product in each
-- # warehouse. This models the many-to-many relationship.
-- #############################################################################
CREATE TABLE inventory (
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (product_id, warehouse_id),

    CONSTRAINT fk_product
        FOREIGN KEY(product_id)
        REFERENCES products(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_warehouse
        FOREIGN KEY(warehouse_id)
        REFERENCES warehouses(id)
        ON DELETE CASCADE,

    CONSTRAINT quantity_non_negative
        CHECK (quantity >= 0)
);

-- #############################################################################
-- # Table: bundle_components
-- # Description: Defines the composition of a bundle product. It links a
-- # 'bundle' product (identified by products.is_bundle = TRUE) to its
-- # 'component' products.
-- #############################################################################
CREATE TABLE bundle_components (
    bundle_product_id INTEGER NOT NULL,
    component_product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,

    PRIMARY KEY (bundle_product_id, component_product_id),

    CONSTRAINT fk_bundle_product
        FOREIGN KEY(bundle_product_id)
        REFERENCES products(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_component_product
        FOREIGN KEY(component_product_id)
        REFERENCES products(id)
        ON DELETE RESTRICT,

    CONSTRAINT quantity_must_be_positive
        CHECK (quantity > 0),

    CONSTRAINT check_self_bundle
        CHECK (bundle_product_id <> component_product_id)
);

-- #############################################################################
-- # Table: inventory_logs
-- # Description: Provides an immutable audit trail of all inventory changes
-- # for traceability and reporting.
-- #############################################################################
CREATE TABLE inventory_logs (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER NOT NULL,
    quantity_change INTEGER NOT NULL,
    reason VARCHAR(255) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Note: A foreign key to `inventory` is omitted here intentionally.
    -- This ensures that logs are preserved as a historical record even if an
    -- inventory item (a product in a warehouse) is deleted.
    -- This preserves the audit trail.
    CONSTRAINT fk_product_log
        FOREIGN KEY(product_id)
        REFERENCES products(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_warehouse_log
        FOREIGN KEY(warehouse_id)
        REFERENCES warehouses(id)
        ON DELETE RESTRICT
);

-- #############################################################################
-- # Indexes
-- # Description: Indexes to improve query performance and enforce uniqueness.
-- # Primary keys and UNIQUE constraints automatically get indexes. Foreign keys
-- # and frequently queried columns are explicitly indexed for performance.
-- #############################################################################
CREATE INDEX idx_warehouses_company_id ON warehouses(company_id);
CREATE INDEX idx_products_supplier_id ON products(supplier_id);
CREATE INDEX idx_inventory_logs_product_warehouse ON inventory_logs(product_id, warehouse_id);
CREATE INDEX idx_inventory_logs_changed_at ON inventory_logs(changed_at);

```

## 2. Identified Gaps & Questions for Product Team

Here is a list of questions for the product team to clarify requirements and ensure the database design aligns with business goals.

*   **On Product-Supplier Relationships:**
    *   Currently, a product can only be linked to a single supplier. Is this intentional, or should the system support sourcing a single product from multiple suppliers? If multiple are needed, how do we determine the primary or default supplier?

*   **On Data Validation and Constraints:**
    *   What are the specific formatting rules for a `sku` (Stock Keeping Unit)? For instance, what is its maximum length and which characters are permitted (e.g., alphanumeric, dashes)?
    *   Are there character length limits or other validation rules for fields like `product.name`, `supplier.name`, or `company.name`?
    *   Is a supplier's `contact_email` a mandatory piece of information for creating a new supplier record?

*   **On Business Logic and Inventory Events:**
    *   Could you provide a complete list of events that should create a record in the `inventory_logs`? We have designed for common cases like 'sale', 'return', 'stock adjustment', and 'initial stock'. Are there others, such as 'transfer between warehouses' or 'damaged goods'?
    *   What is the desired workflow when a user attempts to delete a product that is part of an active bundle? The current design restricts this to protect data integrity, but what process should the user follow to resolve this?
    *   When a bundle product is sold, should the inventory levels of its individual component products be automatically decremented? The current schema assumes this is the case, treating bundles as logical groupings rather than separately stocked items.

*   **On Future Requirements:**
    *   Do you anticipate needing different types of warehouses in the future (e.g., 'Distribution Center', 'Retail Store', 'Virtual') that might have unique properties?
    *   Similarly, should we plan for different classifications of products (e.g., 'Serialized Items', 'Raw Materials', 'Finished Goods') that would require additional, type-specific fields?
    *   Will the system need to support user roles and permissions (e.g., an 'Admin' who can see all company data vs. a 'Warehouse Manager' who can only manage inventory for their specific location)?

## 3. Design Decisions & Justifications

This section explains the key architectural and design choices made for the StockFlow database schema.

*   **Normalization and Scalability:**
    *   **`inventory` as a Junction Table:** We resolved the many-to-many relationship between `products` and `warehouses` using the `inventory` junction table. A product can exist in many warehouses, and a warehouse can hold many products. This normalized design is highly scalable and avoids the data duplication and inflexibility that would result from placing a `warehouse_id` directly in the `products` table.
    *   **Multi-Tenancy (`companies` and `warehouses`):** By creating a `companies` table and linking `warehouses` to it via a `company_id` foreign key, the schema is designed for multi-tenancy from the ground up. This ensures that data is properly segregated, allowing the application to serve multiple businesses where each can only access its own warehouse and inventory data.

*   **Indexing Strategy for Performance and Integrity:**
    *   **Primary Keys:** Every table has a primary key, which automatically creates a unique index. This is essential for uniquely identifying rows and is the foundation for creating relationships.
    *   **Foreign Keys:** We explicitly created indexes on foreign key columns (e.g., `idx_warehouses_company_id`, `idx_products_supplier_id`). These indexes are crucial for accelerating `JOIN` operations, which are fundamental to querying relational data.
    *   **Unique Business Keys:** A `UNIQUE` constraint is placed on `products.sku`. While `products.id` is the surrogate primary key, the `sku` is the natural key used in business operations. This index enforces the critical business rule that every SKU must be unique and provides fast product lookups by SKU.

*   **Data Integrity and Consistency:**
    *   **`NOT NULL` Constraints:** These are applied to essential columns like `products.name` and `inventory.quantity` to guarantee that core data is always present and prevent incomplete or invalid records.
    *   **Foreign Key Constraints:** These enforce referential integrity across the database. For instance, the system prevents the creation of an inventory record for a `product_id` that does not exist in the `products` table.
    *   **`ON DELETE` Policies:** The policies were chosen deliberately. We use `ON DELETE RESTRICT` for critical relationships to prevent accidental data loss. For example, a `supplier` cannot be deleted if they are still linked to products. This forces a deliberate action to reassign those products first. Conversely, `ON DELETE CASCADE` is used on `inventory` records; if a product or warehouse is deleted, its associated inventory entries are cleanly and automatically removed.

*   **Choice of Data Types:**
    *   **`DECIMAL` for Currency:** The `price` column uses `DECIMAL(10, 2)`. Unlike floating-point types (`FLOAT`, `REAL`), which can introduce small rounding errors, `DECIMAL` stores currency values with exact precision, which is non-negotiable for financial data.
    *   **`TIMESTAMP WITH TIME ZONE` for Timestamps:** Using `TIMESTAMPTZ` ensures all timestamps are stored in a consistent, timezone-aware format (typically UTC). This prevents ambiguity and makes it easy to convert to the correct local time for any user or service, regardless of its location.
    *   **`SERIAL` / `BIGSERIAL` for Primary Keys:** These PostgreSQL-specific types provide an efficient and simple way to auto-generate incrementing integer primary keys. `BIGSERIAL` was chosen for `inventory_logs` in anticipation of this table growing very large over time, as every stock movement creates a new row.
