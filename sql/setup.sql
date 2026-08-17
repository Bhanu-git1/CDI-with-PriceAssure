-- ====================================================================
-- Final DCE Database Setup Script (Use Cases 1, 2, 3, 4 & 5)
-- Database: mcp_poc_db
-- ====================================================================

-- 1. Create the Database
CREATE DATABASE IF NOT EXISTS mcp_poc_db;
USE mcp_poc_db;

-- 2. Drop existing tables if they exist (clean slate)
DROP TABLE IF EXISTS salesforce_sync_log;
DROP TABLE IF EXISTS medicine_extraction_log;
DROP TABLE IF EXISTS Transcript_Extraction_History;
DROP TABLE IF EXISTS Tablet_Extract_History;
DROP TABLE IF EXISTS hcp_master_workdetails_history;
DROP TABLE IF EXISTS hcp_master_details;
DROP TABLE IF EXISTS rep_details;
DROP TABLE IF EXISTS rep_master;
DROP TABLE IF EXISTS fatigue_score;
DROP TABLE IF EXISTS hcp_engagement_logs;
DROP TABLE IF EXISTS Compliance_Table;
DROP TABLE IF EXISTS leakage_history;
DROP TABLE IF EXISTS Reverse_Claims;
DROP TABLE IF EXISTS Leakage_Activity;

-- ----------------------------------------------------
-- 3. Create Tables for Use Cases 1, 2, 3, 4 & 5
-- ----------------------------------------------------

-- UC1: Leakage_Activity
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

-- UC1: Reverse_Claims
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

-- UC1: leakage_history
CREATE TABLE leakage_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    previous_value DECIMAL(10, 2),
    new_value DECIMAL(10, 2) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC1: Compliance_Table
CREATE TABLE Compliance_Table (
    Patient_Token VARCHAR(100) PRIMARY KEY,
    Payer_id VARCHAR(50) NOT NULL,
    Payer_Type VARCHAR(50) NOT NULL,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC2: hcp_engagement_logs
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

-- UC2: fatigue_score
CREATE TABLE fatigue_score (
    Fatigue_ID INT AUTO_INCREMENT PRIMARY KEY,
    HCP_Name VARCHAR(100) NOT NULL,
    Fatigue DECIMAL(5, 2) NOT NULL,
    Product VARCHAR(100) NOT NULL,
    Campaign_Name VARCHAR(100) NOT NULL,
    Processed_TimeStamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC3 & UC5: rep_master (Managers)
CREATE TABLE rep_master (
    rep_id VARCHAR(20) PRIMARY KEY,
    rep_firstName VARCHAR(50) NOT NULL,
    rep_lastName VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(30)
);

-- UC3 & UC5: rep_details (Sales Reps)
CREATE TABLE rep_details (
    rep_id VARCHAR(20) PRIMARY KEY,
    rep_firstName VARCHAR(50) NOT NULL,
    rep_lastName VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(30),
    manager_id VARCHAR(20),
    FOREIGN KEY (manager_id) REFERENCES rep_master(rep_id) ON DELETE SET NULL
);

-- UC3 & UC5 Primary: hcp_master_details
CREATE TABLE hcp_master_details (
    hcp_detail_id INT AUTO_INCREMENT PRIMARY KEY,
    hcp_id VARCHAR(50),
    Prescriber_NPI VARCHAR(20) NOT NULL,
    hcp_firstName VARCHAR(50) NOT NULL,
    hcp_lastName VARCHAR(50) NOT NULL,
    rep_id VARCHAR(20),
    status VARCHAR(20) DEFAULT 'In-Progress',
    work_detail TEXT,
    sf_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (rep_id) REFERENCES rep_details(rep_id) ON DELETE SET NULL
);

-- UC3 Audit Log: hcp_master_workdetails_history
CREATE TABLE hcp_master_workdetails_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    hcp_id VARCHAR(50),
    rep_id VARCHAR(20),
    rep_firstName VARCHAR(50),
    rep_lastName VARCHAR(50),
    work_detail TEXT,
    updated_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC4: Tablet_Extract_History (Medicine Extraction)
CREATE TABLE Tablet_Extract_History (
    id INT AUTO_INCREMENT PRIMARY KEY,
    Tablet_name VARCHAR(100) NOT NULL,
    Dosage VARCHAR(50),
    Frequency VARCHAR(50),
    guidance TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    sf_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'Extracted',
    message TEXT
);

-- UC4: Transcript_Extraction_History
CREATE TABLE Transcript_Extraction_History (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hcp_detail_id INT NOT NULL,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    sf_id VARCHAR(50),
    transcript_text TEXT,
    tablet_names VARCHAR(255),
    status VARCHAR(20) DEFAULT 'Processed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC4 Summary: medicine_extraction_log
CREATE TABLE medicine_extraction_log (
    extraction_id INT AUTO_INCREMENT PRIMARY KEY,
    hcp_detail_id INT NOT NULL,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    HCP_Name VARCHAR(100) NOT NULL,
    extracted_drug VARCHAR(100) NOT NULL,
    brand_name VARCHAR(100),
    generic_name VARCHAR(100),
    dosage VARCHAR(50),
    frequency VARCHAR(50),
    confidence_score DECIMAL(5, 2) DEFAULT 0.95,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UC5: salesforce_sync_log (Salesforce CRM Audit)
CREATE TABLE salesforce_sync_log (
    sync_id INT AUTO_INCREMENT PRIMARY KEY,
    hcp_detail_id INT NOT NULL,
    Prescriber_NPI VARCHAR(20) NOT NULL,
    HCP_Name VARCHAR(100) NOT NULL,
    sf_object_type VARCHAR(50) DEFAULT 'Work_Detail__c',
    sf_record_id VARCHAR(50),
    sync_status VARCHAR(20) NOT NULL DEFAULT 'Synced',
    sync_message TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------
-- 4. Seed Sample Data Across All Use Cases
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

INSERT INTO rep_master (rep_id, rep_firstName, rep_lastName, email, phone) VALUES
('MGR_1001', 'John', 'Smith', 'john.smith@pharmacorp.com', '+1-555-0199');

INSERT INTO rep_details (rep_id, rep_firstName, rep_lastName, email, phone, manager_id) VALUES
('2006', 'Alice', 'Johnson', 'alice.j@pharmacorp.com', '+1-555-0201', 'MGR_1001'),
('2007', 'Bob', 'Davis', 'bob.d@pharmacorp.com', '+1-555-0202', 'MGR_1001');

INSERT INTO hcp_master_details (hcp_id, Prescriber_NPI, hcp_firstName, hcp_lastName, rep_id, status, work_detail, sf_id) VALUES
('HCP_101', 'NPI_11111', 'John', 'Smith', '2006', 'Completed', 'Dr. John Smith requested clinical sample for Dolo 650 and expressed interest in Oncology digital webinars.', 'a018W00000XyZ123'),
('HCP_102', 'NPI_22222', 'Sarah', 'Connor', '2006', 'In-Progress', 'Discussed Pan 40 prescription guidelines and co-pay assistance for cardiology patients.', 'a018W00000XyZ124'),
('HCP_103', 'NPI_33333', 'Robert', 'Bruce', '2007', 'In-Progress', 'Provided Atorvas 20 documentation and reviewed patient adherence report.', 'a018W00000XyZ125');

INSERT INTO hcp_master_workdetails_history (hcp_id, rep_id, rep_firstName, rep_lastName, work_detail) VALUES
('HCP_101', '2006', 'Alice', 'Johnson', 'Initial sample request created for Dolo 650.'),
('HCP_102', '2006', 'Alice', 'Johnson', 'Updated Pan 40 discussion notes.');

INSERT INTO Tablet_Extract_History (Tablet_name, Dosage, Frequency, guidance, Prescriber_NPI, sf_id, status, message) VALUES
('Dolo 650', '650mg', 'Twice daily', 'Administer after meals with water', 'NPI_11111', 'a018W00000XyZ123', 'Extracted', 'Successfully extracted from voice transcript'),
('Pan 40', '40mg', 'Once daily before breakfast', 'Take on empty stomach 30 mins prior to food', 'NPI_22222', 'a018W00000XyZ124', 'Extracted', 'Successfully extracted from voice transcript'),
('Atorvas 20', '20mg', 'At bedtime', 'Monitor lipid profile every 3 months', 'NPI_33333', 'a018W00000XyZ125', 'Extracted', 'Successfully extracted from voice transcript');

INSERT INTO Transcript_Extraction_History (hcp_detail_id, Prescriber_NPI, sf_id, transcript_text, tablet_names, status) VALUES
(1, 'NPI_11111', 'a018W00000XyZ123', 'Dr. John Smith requested clinical sample for Dolo 650.', 'Dolo 650', 'Processed'),
(2, 'NPI_22222', 'a018W00000XyZ124', 'Discussed Pan 40 prescription guidelines.', 'Pan 40', 'Processed');

INSERT INTO medicine_extraction_log (hcp_detail_id, Prescriber_NPI, HCP_Name, extracted_drug, brand_name, generic_name, dosage, frequency, confidence_score) VALUES
(1, 'NPI_11111', 'Dr. John Smith', 'Dolo 650', 'Dolo 650', 'Paracetamol', '650mg', 'Twice daily', 98.50),
(2, 'NPI_22222', 'Dr. Sarah Connor', 'Pan 40', 'Pan 40', 'Pantoprazole', '40mg', 'Once daily before breakfast', 96.00),
(3, 'NPI_33333', 'Dr. Robert Bruce', 'Atorvas 20', 'Atorvas 20', 'Atorvastatin', '20mg', 'At bedtime', 94.20);

INSERT INTO salesforce_sync_log (hcp_detail_id, Prescriber_NPI, HCP_Name, sf_object_type, sf_record_id, sync_status, sync_message) VALUES
(1, 'NPI_11111', 'Dr. John Smith', 'Work_Detail__c', 'a018W00000XyZ123', 'Synced', 'Successfully pushed to Salesforce CRM'),
(2, 'NPI_22222', 'Dr. Sarah Connor', 'Work_Detail__c', 'a018W00000XyZ124', 'Synced', 'Successfully pushed to Salesforce CRM'),
(3, 'NPI_33333', 'Dr. Robert Bruce', 'Work_Detail__c', NULL, 'Pending', 'Scheduled for next sync batch');

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
