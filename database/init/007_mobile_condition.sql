CREATE TABLE mobile_condition (
    condition_id SERIAL PRIMARY KEY,
    evaluation_id INT,
    screen_condition VARCHAR(100),
    body_condition VARCHAR(100),
    battery_health INT,
    camera_condition VARCHAR(100),
    speaker_condition VARCHAR(100),
    charging_condition VARCHAR(100),
    overall_condition VARCHAR(100),
    defects TEXT,
    condition_score INT
);