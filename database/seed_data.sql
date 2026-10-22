-- ============================================================================
-- CoherentMobiles Database Seed Script
-- Minimal dataset (4-6 records per table) optimized for practicing SQL JOINs
-- Target Tables: brands, phone_series, phone_models, phone_variants, users, auth_sessions
-- ============================================================================

BEGIN;

-- 1. Reset all tables to ensure only the requested tables contain data
TRUNCATE TABLE
    appointments,
    auth_sessions,
    brands,
    estimations,
    exchange_details,
    feedback,
    imei_details,
    mobile_condition,
    mobile_images,
    order_items,
    orders,
    phone_evaluations,
    phone_models,
    phone_series,
    phone_variants,
    pricing,
    users,
    valuations
RESTART IDENTITY CASCADE;

-- 2. Seed BRANDS (5 records)
INSERT INTO brands (brand_name) VALUES
('Apple'),
('Samsung'),
('Google'),
('OnePlus'),
('Xiaomi');

-- 3. Seed PHONE SERIES (5 records)
-- Note: Xiaomi (brand_id 5) intentionally has no series to demonstrate LEFT JOIN
INSERT INTO phone_series (brand_id, series_name) VALUES
(1, 'iPhone 15 Series'),
(1, 'iPhone 16 Series'),
(2, 'Galaxy S Series'),
(3, 'Pixel 8 Series'),
(4, 'Nord Series');

-- 4. Seed PHONE MODELS (5 records)
-- Note: Nord Series (series_id 5) intentionally has no models to demonstrate LEFT JOIN
INSERT INTO phone_models (series_id, model_name, image_url) VALUES
(1, 'iPhone 15', '/images/iphone-15.png'),
(2, 'iPhone 16', '/images/iphone-16.png'),
(2, 'iPhone 16 Pro', '/images/iphone-16-pro.png'),
(3, 'Galaxy S24', '/images/galaxy-s24.png'),
(4, 'Pixel 8', '/images/pixel-8.png');

-- 5. Seed PHONE VARIANTS (6 records)
-- Note: Pixel 8 (model_id 5) intentionally has no variants to demonstrate LEFT JOIN
INSERT INTO phone_variants 
(model_id, storage_gb, ram_gb, color, battery_capacity, listed_price, rating, stock_quantity) 
VALUES
(1, 128, 6,  'Black',            3349,  69999.00, 4.50, 10),
(1, 256, 6,  'Blue',             3349,  79999.00, 4.60,  8),
(2, 128, 8,  'White',            3561,  79999.00, 4.60, 15),
(3, 256, 8,  'Natural Titanium', 3582, 119999.00, 4.80,  5),
(4, 256, 8,  'Onyx Black',       4000,  74999.00, 4.50, 12),
(4, 512, 12, 'Cobalt Violet',    4000,  89999.00, 4.70,  4);

-- 6. Seed USERS (5 records)
INSERT INTO users (name, email, phone, password_hash, address, created_at) VALUES
('Rahul Kumar',  'rahul@example.com',  '+919876543210', '$2a$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWyFp0gA2c7y8re', 'Bengaluru, Karnataka', '2026-01-15 10:30:00'),
('Priya Sharma', 'priya@example.com',  '+919876543211', '$2a$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWyFp0gA2c7y8re', 'Mumbai, Maharashtra',   '2026-02-01 11:15:00'),
('Arjun Rao',    'arjun@example.com',  '+919876543212', '$2a$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWyFp0gA2c7y8re', 'Hyderabad, Telangana', '2026-02-18 14:20:00'),
('Sneha Patel',  'sneha@example.com',  '+919876543213', '$2a$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWyFp0gA2c7y8re', 'Ahmedabad, Gujarat',    '2026-03-05 09:45:00'),
('Vikram Singh', 'vikram@example.com', '+919876543214', '$2a$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWyFp0gA2c7y8re', 'New Delhi, Delhi',     '2026-03-20 16:00:00');

-- 7. Seed AUTH_SESSIONS (5 records)
-- Note: Vikram Singh (user_id 5) intentionally has no sessions; Rahul Kumar (user_id 1) has 2 sessions
INSERT INTO auth_sessions (user_id, login_method, otp_verified, created_at, expires_at) VALUES
(1, 'email_password', true,  '2026-03-21 08:00:00', '2026-03-22 08:00:00'),
(1, 'google_oauth',   true,  '2026-03-21 09:30:00', '2026-03-22 09:30:00'),
(2, 'phone_otp',      true,  '2026-03-21 10:15:00', '2026-03-22 10:15:00'),
(3, 'email_password', false, '2026-03-21 11:00:00', '2026-03-21 11:15:00'),
(4, 'phone_otp',      true,  '2026-03-21 12:00:00', '2026-03-22 12:00:00');

COMMIT;
