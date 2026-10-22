CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    order_reference VARCHAR(50) UNIQUE,
    subtotal NUMERIC(10,2),
    trade_in_credit NUMERIC(10,2),
    coupon_discount NUMERIC(10,2),
    total_amount NUMERIC(10,2),
    delivery_address TEXT,
    order_status VARCHAR(50),
    order_date TIMESTAMP
);