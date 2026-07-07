-- 1. Create the Database
CREATE DATABASE IF NOT EXISTS mcp_poc_db;
USE mcp_poc_db;

-- 2. Drop existing tables if they exist (clean slate)
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

-- 3. Create Users Table
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    signup_date DATE NOT NULL
);

-- 4. Create Products Table
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stock INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Create Orders Table
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    order_date DATE NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(30) DEFAULT 'Pending',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 6. Create Order Items Table
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- 7. Seed Sample Data
INSERT INTO users (name, email, status, signup_date) VALUES
('John Doe', 'john.doe@example.com', 'active', '2026-01-15'),
('Jane Smith', 'jane.smith@example.com', 'active', '2026-02-10'),
('Bob Johnson', 'bob.johnson@example.com', 'inactive', '2026-03-01'),
('Alice Brown', 'alice.brown@example.com', 'active', '2026-03-15'),
('Charlie Wilson', 'charlie.w@example.com', 'active', '2026-04-20');

INSERT INTO products (name, category, price, stock) VALUES
('Wireless Mouse', 'Electronics', 29.99, 150),
('Mechanical Keyboard', 'Electronics', 89.99, 45),
('HD Monitor 27"', 'Electronics', 199.99, 20),
('Ergonomic Office Chair', 'Furniture', 249.99, 15),
('Standing Desk', 'Furniture', 399.99, 10),
('Coffee Mug', 'Kitchen', 12.50, 200),
('Notebook A5', 'Stationery', 6.99, 500);

INSERT INTO orders (user_id, order_date, total_amount, status) VALUES
(1, '2026-05-01', 119.98, 'Shipped'),
(2, '2026-05-10', 212.49, 'Shipped'),
(4, '2026-05-15', 399.99, 'Processing'),
(1, '2026-06-01', 42.49, 'Delivered'),
(3, '2026-06-12', 12.50, 'Cancelled'),
(5, '2026-06-20', 289.97, 'Shipped');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 29.99),
(1, 2, 1, 89.99),
(2, 2, 1, 89.99),
(2, 6, 1, 12.50),
(2, 7, 1, 6.99),
(2, 1, 3, 29.99), -- 3 Wireless Mice
(3, 5, 1, 399.99),
(4, 1, 1, 29.99),
(4, 6, 1, 12.50),
(5, 6, 1, 12.50),
(6, 4, 1, 249.99),
(6, 1, 1, 29.99),
(6, 7, 1, 6.99);

-- 8. Create Secure, Read-Only User for MCP Server
-- Feel free to adjust names/passwords to match your local setup
-- Note: Run these lines individually if your server requires specific host mapping (e.g. '%' instead of 'localhost')
DROP USER IF EXISTS 'mcp_readonly'@'localhost';
CREATE USER 'mcp_readonly'@'localhost' IDENTIFIED BY 'mcp_secure_pass123';
GRANT SELECT ON mcp_poc_db.* TO 'mcp_readonly'@'localhost';
FLUSH PRIVILEGES;

-- Alternative creation for universal host connectivity (useful for Docker/remote testing)
DROP USER IF EXISTS 'mcp_readonly'@'%';
CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'mcp_secure_pass123';
GRANT SELECT ON mcp_poc_db.* TO 'mcp_readonly'@'%';
FLUSH PRIVILEGES;
