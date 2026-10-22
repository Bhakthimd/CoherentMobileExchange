CREATE TABLE phone_evaluations (
    evaluation_id SERIAL PRIMARY KEY,
    user_id INT,
    variant_id INT,
    imei_id INT,
    feature_score INT,
    condition_score INT,
    performance_score INT,
    overall_score INT,
    evaluation_date TIMESTAMP
);