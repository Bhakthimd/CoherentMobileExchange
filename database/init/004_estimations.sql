CREATE TABLE estimations (
    estimation_id SERIAL PRIMARY KEY,
    variant_id INT,
    expected_selling_price DECIMAL(10,2),
    estimated_repair_cost DECIMAL(10,2),
    estimated_resale_price DECIMAL(10,2),
    estimation_date TIMESTAMP,
    exchange_id INT
);