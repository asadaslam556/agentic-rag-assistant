-- Sample orders database for the sql_query tool. Fictional, like the rest
-- of the sample corpus. Loaded into an in-memory SQLite database at startup,
-- so nothing is written to disk and every run starts from the same data.
--
-- Worked examples. The planner sees them next to the schema, and the
-- offline mock answers questions that closely match one of them.
-- Q: Which customer ordered the most robots?
-- SQL: SELECT c.name, SUM(o.quantity) AS robots_ordered FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.name ORDER BY robots_ordered DESC LIMIT 1
-- Q: How many orders are still open?
-- SQL: SELECT COUNT(*) AS open_orders FROM orders WHERE status = 'open'
-- Q: What was the total revenue from orders in 2025?
-- SQL: SELECT SUM(quantity * unit_price_eur) AS revenue_eur FROM orders WHERE order_date LIKE '2025-%'

CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT NOT NULL,
  industry TEXT NOT NULL
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  sku TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price_eur INTEGER NOT NULL,
  order_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'shipped', 'delivered'))
);

INSERT INTO customers (id, name, country, industry) VALUES
  (1, 'Nordlicht Logistik', 'Germany', 'logistics'),
  (2, 'Brennero Freight', 'Italy', 'logistics'),
  (3, 'Kestrel Pharma', 'Switzerland', 'pharmaceuticals'),
  (4, 'Tallinn Cold Chain', 'Estonia', 'food'),
  (5, 'Vargas Automotive', 'Spain', 'automotive');

-- unit_price_eur below the ATLAS-P2 list price of 38500 is a volume discount
INSERT INTO orders (id, customer_id, sku, quantity, unit_price_eur, order_date, status) VALUES
  (1, 1, 'ATLAS-P2', 12, 38500, '2025-02-14', 'delivered'),
  (2, 2, 'ATLAS-P2', 8, 38500, '2025-04-03', 'delivered'),
  (3, 3, 'ATLAS-P1', 5, 24900, '2025-05-20', 'delivered'),
  (4, 1, 'ATLAS-P2', 20, 36575, '2025-09-09', 'delivered'),
  (5, 4, 'ATLAS-P2', 6, 38500, '2025-11-28', 'shipped'),
  (6, 5, 'ATLAS-P2', 15, 37345, '2026-01-15', 'open'),
  (7, 3, 'ATLAS-P2', 4, 38500, '2026-03-02', 'open');
