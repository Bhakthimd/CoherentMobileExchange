CREATE TABLE appointments (
    appointment_id SERIAL PRIMARY KEY,
    user_id INT,
    order_id INT,
    appointment_date DATE,
    appointment_time TIME,
    location VARCHAR(100),
    verification_method VARCHAR(50),
    reference_number VARCHAR(50) UNIQUE,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);