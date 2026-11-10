-- The schema of a small online shop. Everything lives in the schema "sqlshow", so `sqlshow init` can drop and rebuild
-- it without touching anything else in the database.
--
-- Only primary keys are declared on purpose: PostgreSQL does not index a foreign key by itself, and the index
-- experiments (`sqlshow bench`) start from exactly this baseline.

CREATE TABLE categories (
    category_id integer PRIMARY KEY,
    parent_id   integer REFERENCES categories (category_id),
    name        text NOT NULL
);

CREATE TABLE products (
    product_id  integer PRIMARY KEY,
    category_id integer NOT NULL REFERENCES categories (category_id),
    name        text NOT NULL,
    price       numeric(10, 2) NOT NULL CHECK (price > 0)
);

CREATE TABLE customers (
    customer_id integer PRIMARY KEY,
    email       text NOT NULL,
    country     text NOT NULL,
    signed_up   date NOT NULL
);

CREATE TABLE orders (
    order_id    integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers (customer_id),
    ordered_at  timestamptz NOT NULL,
    status      text NOT NULL CHECK (status IN ('paid', 'shipped', 'refunded', 'cancelled', 'pending'))
);

CREATE TABLE order_items (
    order_id   integer NOT NULL REFERENCES orders (order_id),
    line_no    smallint NOT NULL,
    product_id integer NOT NULL REFERENCES products (product_id),
    quantity   smallint NOT NULL CHECK (quantity > 0),
    unit_price numeric(10, 2) NOT NULL CHECK (unit_price > 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE events (
    event_id    bigint PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers (customer_id),
    occurred_at timestamptz NOT NULL,
    kind        text NOT NULL,
    props       jsonb NOT NULL
);

-- What was sold: one row per order line of an order that counts as revenue (paid or shipped).
CREATE VIEW sales AS
SELECT oi.order_id,
       o.customer_id,
       o.ordered_at,
       oi.product_id,
       p.category_id,
       oi.quantity,
       oi.quantity * oi.unit_price AS amount
FROM order_items AS oi
JOIN orders AS o USING (order_id)
JOIN products AS p USING (product_id)
WHERE o.status IN ('paid', 'shipped');

-- How the data was made (scale, seed): read back by `sqlshow evaluate` for the report.
CREATE TABLE meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);
