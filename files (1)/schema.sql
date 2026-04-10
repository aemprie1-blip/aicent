-- ============================================================
-- Phase 1: Database Architecture — Supabase PostgreSQL Schema
-- Restaurant AI Call Center — Jordan Market
-- ============================================================

-- 1. Menu Items
CREATE TABLE menu_items (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,                   -- Arabic name e.g. "شاورما دجاج"
    name_en     TEXT,                            -- Optional English fallback
    price       NUMERIC(8,2) NOT NULL,           -- JOD
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    category    TEXT NOT NULL DEFAULT 'عام',      -- e.g. "مشاوي", "مشروبات", "حلويات"
    image_url   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed some sample items
INSERT INTO menu_items (name, price, category) VALUES
    ('شاورما دجاج',       1.50, 'ساندويشات'),
    ('شاورما لحمة',       2.00, 'ساندويشات'),
    ('فلافل ساندويش',     0.75, 'ساندويشات'),
    ('حمص',               1.25, 'مقبلات'),
    ('فتوش',              1.50, 'مقبلات'),
    ('مشاوي مشكلة',       7.00, 'مشاوي'),
    ('كباب',              5.00, 'مشاوي'),
    ('منسف',              8.00, 'أطباق رئيسية'),
    ('مقلوبة',            6.00, 'أطباق رئيسية'),
    ('بيبسي',             0.50, 'مشروبات'),
    ('عصير برتقال طازج',  1.00, 'مشروبات'),
    ('كنافة',             2.50, 'حلويات');

-- 2. Customers (phone as PK — E.164 format)
CREATE TABLE customers (
    phone_number TEXT PRIMARY KEY,               -- e.g. "+962791234567"
    name         TEXT,
    last_address TEXT,
    order_count  INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Orders
CREATE TABLE orders (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_phone  TEXT REFERENCES customers(phone_number),
    items           JSONB NOT NULL DEFAULT '[]',  -- [{name, qty, unit_price}]
    total_price     NUMERIC(10,2) NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'new',  -- new → preparing → ready → delivered → cancelled
    delivery_address TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at DESC);

-- 4. Enable Supabase Realtime on the orders table
ALTER PUBLICATION supabase_realtime ADD TABLE orders;

-- 5. Auto-increment customer order_count on new order
CREATE OR REPLACE FUNCTION increment_order_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE customers
    SET order_count = order_count + 1,
        updated_at  = now()
    WHERE phone_number = NEW.customer_phone;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_increment_order_count
AFTER INSERT ON orders
FOR EACH ROW
EXECUTE FUNCTION increment_order_count();

-- 6. Row Level Security (basic — dashboard uses service_role key)
ALTER TABLE menu_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders     ENABLE ROW LEVEL SECURITY;

-- Allow authenticated (dashboard) users full access
CREATE POLICY "Authenticated full access" ON menu_items
    FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated full access" ON customers
    FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated full access" ON orders
    FOR ALL USING (auth.role() = 'authenticated');

-- Service role (backend) bypasses RLS automatically
