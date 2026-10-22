CREATE TABLE exchange_details (
    exchange_id SERIAL PRIMARY KEY,
    user_id INT,
    old_variant_id INT,
    new_variant_id INT,
    evaluation_id INT,
    exchange_credit DECIMAL(10,2),
    exchange_status VARCHAR(50),
    credited_at TIMESTAMP
);