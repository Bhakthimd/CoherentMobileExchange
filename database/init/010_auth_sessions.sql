CREATE TABLE auth_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    login_method VARCHAR(50),
    otp_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);