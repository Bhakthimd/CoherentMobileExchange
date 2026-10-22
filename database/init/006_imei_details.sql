CREATE TABLE imei_details (
    imei_id SERIAL PRIMARY KEY,
    user_id INT,
    variant_id INT,
    imei_number VARCHAR(20) UNIQUE,
    validation_status VARCHAR(50),
    device_eligibility VARCHAR(50),
    validation_source VARCHAR(100),
    validated_at TIMESTAMP
);