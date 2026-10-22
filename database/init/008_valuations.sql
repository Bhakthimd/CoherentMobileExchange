CREATE TABLE valuations (
    valuation_id SERIAL PRIMARY KEY,
    evaluation_id INT,
    original_value DECIMAL(10,2),
    depreciation DECIMAL(10,2),
    repair_cost DECIMAL(10,2),
    resale_value DECIMAL(10,2),
    final_valuation DECIMAL(10,2),
    valuation_date TIMESTAMP,
    imei_id INT
);