CREATE TABLE feedback (
    feedback_id SERIAL PRIMARY KEY,
    user_id INT,
    evaluation_id INT,
    rating INT,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (evaluation_id)
        REFERENCES phone_evaluations(evaluation_id)
);