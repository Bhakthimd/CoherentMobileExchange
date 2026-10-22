CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(order_id),
    variant_id INT REFERENCES phone_variants(variant_id),
    quantity INT,
    unit_price NUMERIC(10,2)
);