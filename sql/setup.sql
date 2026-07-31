-- 1. Create the Database
CREATE DATABASE IF NOT EXISTS mcp_poc_db;
USE mcp_poc_db;

-- 2. Drop existing tables if they exist (clean slate)
DROP TABLE IF EXISTS fatigue_score;
DROP TABLE IF EXISTS hcp_engagement_logs;
DROP TABLE IF EXISTS Compliance_Table;
DROP TABLE IF EXISTS leakage_history;
DROP TABLE IF EXISTS Reverse_Claims;
DROP TABLE IF EXISTS Leakage_Activity;

-- Also drop e-commerce tables if recreating
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

-- ----------------------------------------------------
-- 3. Create Commercial Command Centre Tables
-- ----------------------------------------------------

-- Table 1: Leakage_Activity
CREATE TABLE Leakage_Activity (
    id INT AUTO_INCREMENT PRIMARY KEY,
    BrandName VARCHAR(100) NOT NULL,
    Pharmacy_ID VARCHAR(50) NOT NULL,
    zip_code VARCHAR(15) NOT NULL,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    HCP_Name VARCHAR(100) NOT NULL,
    State VARCHAR(10) NOT NULL,
    Pharmacy_Rejections INT DEFAULT 0,
    Total_Brand_Rejections INT DEFAULT 0,
    Leakage_Percentage DECIMAL(5, 2) DEFAULT 0.00,
    generic_name VARCHAR(100),
    manufacturer VARCHAR(100),
    productid VARCHAR(50),
    Processed_TimeStamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Reverse_Claims
CREATE TABLE Reverse_Claims (
    id INT AUTO_INCREMENT PRIMARY KEY,
    Transaction_ID VARCHAR(50) NOT NULL,
    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Patient_Token VARCHAR(100) NOT NULL,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    Pharmacy_ID VARCHAR(50) NOT NULL,
    NDC_Code VARCHAR(30) NOT NULL,
    Payer_BIN VARCHAR(30) NOT NULL,
    Response_Status VARCHAR(20) NOT NULL,
    Reject_Code VARCHAR(20),
    Reject_Message TEXT,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: leakage_history
CREATE TABLE leakage_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    previous_value DECIMAL(10, 2),
    new_value DECIMAL(10, 2) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 4: Compliance_Table
CREATE TABLE Compliance_Table (
    Patient_Token VARCHAR(100) PRIMARY KEY,
    Payer_id VARCHAR(50) NOT NULL,
    Payer_Type VARCHAR(50) NOT NULL,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 5: hcp_engagement_logs
CREATE TABLE hcp_engagement_logs (
    Log_ID INT AUTO_INCREMENT PRIMARY KEY,
    HCP_ID VARCHAR(50) NOT NULL,
    Engagement_Date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Channel VARCHAR(50) NOT NULL,
    Email_Sent INT DEFAULT 0,
    Email_Opened INT DEFAULT 0,
    Email_Clicked INT DEFAULT 0,
    Webinar_Minutes INT DEFAULT 0,
    Campaign_ID VARCHAR(50) NOT NULL
);

-- Table 6: fatigue_score
CREATE TABLE fatigue_score (
    Fatigue_ID INT AUTO_INCREMENT PRIMARY KEY,
    HCP_Name VARCHAR(100) NOT NULL,
    Fatigue DECIMAL(5, 2) NOT NULL,
    Product VARCHAR(100) NOT NULL,
    Campaign_Name VARCHAR(100) NOT NULL,
    Processed_TimeStamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------
-- 4. Seed Sample Data
-- ----------------------------------------------------

INSERT INTO Leakage_Activity (BrandName, Pharmacy_ID, zip_code, Prescriber_NPI, HCP_Name, State, Pharmacy_Rejections, Total_Brand_Rejections, Leakage_Percentage, generic_name, manufacturer, productid) VALUES
('OncoShield', 'PHARM_101', '90210', 'NPI_11111', 'Dr. John Smith', 'CA', 12, 50, 24.00, 'onco_gen', 'PharmaCorp', 'PROD_01'),
('OncoShield', 'PHARM_102', '90211', 'NPI_22222', 'Dr. Sarah Connor', 'CA', 8, 40, 20.00, 'onco_gen', 'PharmaCorp', 'PROD_01'),
('CardioGuard', 'PHARM_103', '60601', 'NPI_33333', 'Dr. Robert Bruce', 'IL', 25, 80, 31.25, 'cardio_gen', 'HealthInc', 'PROD_02'),
('ImmunoFlex', 'PHARM_104', '75001', 'NPI_44444', 'Dr. Emily Watson', 'TX', 15, 30, 50.00, 'immuno_gen', 'BioGen', 'PROD_03');

INSERT INTO Reverse_Claims (Transaction_ID, Patient_Token, Prescriber_NPI, Pharmacy_ID, NDC_Code, Payer_BIN, Response_Status, Reject_Code, Reject_Message) VALUES
('TXN_9001', 'PAT_001', 'NPI_11111', 'PHARM_101', '12345-678-90', 'BIN_610014', 'REJECTED', '75', 'Prior Authorization Required'),
('TXN_9002', 'PAT_002', 'NPI_22222', 'PHARM_102', '12345-678-90', 'BIN_610014', 'REJECTED', '70', 'Plan Limit Exceeded'),
('TXN_9003', 'PAT_003', 'NPI_33333', 'PHARM_103', '98765-432-10', 'BIN_004336', 'REVERSED', '75', 'Prior Authorization Required');

INSERT INTO leakage_history (previous_value, new_value, updated_by, updated_at) VALUES
(15.00, 20.00, 'admin_user', '2026-07-01 10:00:00'),
(20.00, 25.00, 'ops_lead', '2026-07-15 14:30:00'),
(25.00, 30.00, 'compliance_mgr', '2026-07-28 09:15:00');

INSERT INTO Compliance_Table (Patient_Token, Payer_id, Payer_Type) VALUES
('PAT_001', 'PAYER_GOV_1', 'MEDICARE'),
('PAT_002', 'PAYER_GOV_2', 'MEDICAID'),
('PAT_003', 'PAYER_COMM_1', 'COMMERCIAL');

INSERT INTO hcp_engagement_logs (HCP_ID, Channel, Email_Sent, Email_Opened, Email_Clicked, Webinar_Minutes, Campaign_ID) VALUES
('HCP_101', 'EMAIL', 10, 8, 4, 0, 'CAMP_2026_Q1'),
('HCP_102', 'WEBINAR', 2, 2, 1, 45, 'CAMP_2026_Q2'),
('HCP_103', 'REP_VISIT', 5, 3, 1, 0, 'CAMP_2026_Q1');

INSERT INTO fatigue_score (HCP_Name, Fatigue, Product, Campaign_Name) VALUES
('Dr. John Smith', 85.50, 'OncoShield', 'Q1 Oncology Digital Drip'),
('Dr. Sarah Connor', 92.00, 'OncoShield', 'Spring Omnichannel Blitz'),
('Dr. Robert Bruce', 45.00, 'CardioGuard', 'Cardio Direct Email'),
('Dr. Emily Watson', 78.20, 'ImmunoFlex', 'Immuno Digital Portal');

-- ----------------------------------------------------
-- 5. Create Secure Read-Only Database User
-- ----------------------------------------------------
DROP USER IF EXISTS 'mcp_readonly'@'localhost';
CREATE USER 'mcp_readonly'@'localhost' IDENTIFIED BY 'mcp_secure_pass123';
GRANT SELECT ON mcp_poc_db.* TO 'mcp_readonly'@'localhost';
FLUSH PRIVILEGES;

DROP USER IF EXISTS 'mcp_readonly'@'%';
CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'mcp_secure_pass123';
GRANT SELECT ON mcp_poc_db.* TO 'mcp_readonly'@'%' ;
FLUSH PRIVILEGES;
