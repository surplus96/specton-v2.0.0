"""New implementation schema exported alongside the immutable source design.

The source tables are provenance, not aliases: generated demo transactions use these
explicitly named derived tables, avoiding fabricated migration of the original model.
"""

from specton.contracts.commerce import CommercePolicy

DDL = """
CREATE TABLE _specton_c_product (
 id text PRIMARY KEY, name text NOT NULL, specification text NOT NULL, barcode text NOT NULL,
 tax text NOT NULL, safety_stock numeric(18,3) NOT NULL CHECK(safety_stock>=0));
CREATE TABLE _specton_c_unit (
 product_id text REFERENCES _specton_c_product, name text,
 factor numeric(18,3) NOT NULL CHECK(factor>0),
 is_default boolean NOT NULL, PRIMARY KEY(product_id,name));
CREATE UNIQUE INDEX _specton_c_default_unit ON _specton_c_unit(product_id) WHERE is_default;
CREATE TABLE _specton_c_member (
 id text PRIMARY KEY, name text NOT NULL, representative text NOT NULL,
 business_number varchar(10) NOT NULL UNIQUE, grade text NOT NULL);
CREATE TABLE _specton_c_lot (
 id text PRIMARY KEY, product_id text NOT NULL REFERENCES _specton_c_product, expires date NOT NULL,
 received numeric(18,3) NOT NULL CHECK(received>0),
 available numeric(18,3) NOT NULL CHECK(available>=0 AND available<=received));
CREATE TABLE _specton_c_order (
 id text PRIMARY KEY, member_id text NOT NULL REFERENCES _specton_c_member,
 created_at timestamptz NOT NULL, status text NOT NULL CHECK(status IN ('accepted','cancelled')),
 total numeric(18,2) NOT NULL CHECK(total>=0));
CREATE TABLE _specton_c_line (
 order_id text REFERENCES _specton_c_order, sequence integer,
 product_id text NOT NULL REFERENCES _specton_c_product, unit text NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0), factor numeric(18,3) NOT NULL CHECK(factor>0),
 price numeric(18,2) NOT NULL CHECK(price>=0), amount numeric(18,2) NOT NULL CHECK(amount>=0),
 PRIMARY KEY(order_id,sequence),
 FOREIGN KEY(product_id,unit) REFERENCES _specton_c_unit(product_id,name));
CREATE TABLE _specton_c_allocation (
 order_id text NOT NULL REFERENCES _specton_c_order, sequence integer NOT NULL,
 lot_id text NOT NULL REFERENCES _specton_c_lot, quantity numeric(18,3) NOT NULL CHECK(quantity>0),
 PRIMARY KEY(order_id,sequence,lot_id),
 FOREIGN KEY(order_id,sequence) REFERENCES _specton_c_line(order_id,sequence));
CREATE TABLE _specton_c_return (
 id text PRIMARY KEY, member_id text NOT NULL REFERENCES _specton_c_member,
 created_at timestamptz NOT NULL,
 amount numeric(18,2) NOT NULL CHECK(amount>0), warning boolean NOT NULL);
"""
ERD = """
    _specton_c_product {
        text id PK
        text name
        text specification
        text barcode
        text tax
        numeric safety_stock
    }
    _specton_c_unit {
        text product_id PK,FK
        text name PK
        numeric factor
        boolean is_default
    }
    _specton_c_member {
        text id PK
        text name
        text representative
        varchar business_number UK
        text grade
    }
    _specton_c_lot {
        text id PK
        text product_id FK
        date expires
        numeric received
        numeric available
    }
    _specton_c_order {
        text id PK
        text member_id FK
        timestamptz created_at
        text status
        numeric total
    }
    _specton_c_line {
        text order_id PK,FK
        integer sequence PK
        text product_id FK
        text unit FK
        numeric quantity
        numeric factor
        numeric price
        numeric amount
    }
    _specton_c_allocation {
        text order_id PK,FK
        integer sequence PK,FK
        text lot_id PK,FK
        numeric quantity
    }
    _specton_c_return {
        text id PK
        text member_id FK
        timestamptz created_at
        numeric amount
        boolean warning
    }
    _specton_c_product ||--o{ _specton_c_unit : units
    _specton_c_product ||--o{ _specton_c_lot : receipts
    _specton_c_member ||--o{ _specton_c_order : orders
    _specton_c_order ||--o{ _specton_c_line : lines
    _specton_c_unit ||--o{ _specton_c_line : unit_conversion
    _specton_c_line ||--o{ _specton_c_allocation : allocation
    _specton_c_lot ||--o{ _specton_c_allocation : stock
    _specton_c_member ||--o{ _specton_c_return : returns
"""


def schema(policy: CommercePolicy) -> tuple[str, str]:
    ddl, erd = DDL, ERD
    if policy.product_note_enabled:
        ddl += "ALTER TABLE _specton_c_product ADD COLUMN note varchar(500) NOT NULL DEFAULT '';\n"
        erd += "    _specton_c_product {\n        varchar note\n    }\n"
    return ddl, erd
