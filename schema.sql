CREATE DATABASE IF NOT EXISTS salon_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE salon_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    duration VARCHAR(50) NOT NULL,
    category VARCHAR(50) DEFAULT 'General',
    image_url VARCHAR(255) DEFAULT '',
    is_active TINYINT(1) DEFAULT 1
);

CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    selected_services TEXT NOT NULL,
    preferred_date DATE NOT NULL,
    preferred_time VARCHAR(20),
    status ENUM('Pending','Confirmed','Cancelled') DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gallery (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    caption VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    `key` VARCHAR(100) PRIMARY KEY,
    value TEXT
);

-- Admin account: username=komali | password=komali123
INSERT IGNORE INTO users (full_name, username, phone, email, password_hash, is_admin)
VALUES ('Komali', 'komali', '0000000000', 'komali@newshades.com',
'$2b$12$zA9WEAEz5EdojsMEXZZ7iuUxep7B/inOz.kiEWIZeDVB9pl1VttYe', 1);

-- Sample services
INSERT IGNORE INTO services (service_name, description, price, duration, category) VALUES
('Hair Cut', 'Professional haircut styled to your preference', 300.00, '30 mins', 'Hair'),
('Beard Trim', 'Clean beard shaping and trimming', 150.00, '20 mins', 'Beard'),
('Hair Color', 'Full hair coloring with premium products', 800.00, '90 mins', 'Hair'),
('Facial', 'Deep cleansing facial treatment', 500.00, '45 mins', 'Skin'),
('Head Massage', 'Relaxing scalp and head massage', 250.00, '30 mins', 'Wellness'),
('Hair Spa', 'Nourishing hair spa treatment', 600.00, '60 mins', 'Hair');
