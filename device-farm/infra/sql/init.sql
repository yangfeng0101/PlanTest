-- Device Farm Database Initialization Script (Phase 3 aligned)
-- PostgreSQL 15

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum Types (Must be created before use in tables)
DO $$ BEGIN
    CREATE TYPE reservationstatus AS ENUM ('pending', 'active', 'completed', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE grouptype AS ENUM ('custom', 'system', 'tag');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(100) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    full_name VARCHAR(200),
    display_name VARCHAR(100),
    avatar_url TEXT,
    role VARCHAR(20) DEFAULT 'user',
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

-- Devices Table (Aligned with DeviceDB in device_svc)
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    model VARCHAR(100) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    os VARCHAR(20) DEFAULT 'android' NOT NULL,
    os_version VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'online' NOT NULL,
    screen_resolution VARCHAR(50) NOT NULL,
    screen_size FLOAT NOT NULL,
    cpu VARCHAR(200) NOT NULL,
    memory VARCHAR(50) NOT NULL,
    storage VARCHAR(50) NOT NULL,
    battery_level INTEGER DEFAULT 100 NOT NULL,
    occupied_by VARCHAR(100),
    occupied_at TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    tags_json TEXT DEFAULT '[]' NOT NULL,
    thumbnail TEXT
);

-- Scripts Table
CREATE TABLE IF NOT EXISTS scripts (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    script_type VARCHAR(20) NOT NULL,
    content TEXT,
    tags JSONB DEFAULT '[]',
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Test Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    script_id VARCHAR(100) REFERENCES scripts(id),
    device_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    result VARCHAR(20),
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Device Reservations Table
CREATE TABLE IF NOT EXISTS device_reservations (
    id VARCHAR(100) PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    purpose TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Device Thresholds Table
CREATE TABLE IF NOT EXISTS device_thresholds (
    id VARCHAR(100) PRIMARY KEY,
    device_id VARCHAR(100) UNIQUE NOT NULL,
    cpu_warning FLOAT DEFAULT 80.0,
    cpu_critical FLOAT DEFAULT 95.0,
    memory_warning FLOAT DEFAULT 80.0,
    memory_critical FLOAT DEFAULT 95.0,
    battery_warning FLOAT DEFAULT 20.0,
    battery_critical FLOAT DEFAULT 10.0,
    temperature_warning FLOAT DEFAULT 45.0,
    temperature_critical FLOAT DEFAULT 55.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Device Groups Table
CREATE TABLE IF NOT EXISTS device_groups (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    type VARCHAR(20) DEFAULT 'custom',
    device_ids_json TEXT DEFAULT '[]' NOT NULL,
    color VARCHAR(20) DEFAULT '#1890ff',
    icon VARCHAR(50),
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reports Table
CREATE TABLE IF NOT EXISTS reports (
    id VARCHAR(100) PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL,
    title VARCHAR(255),
    description TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    format VARCHAR(20) DEFAULT 'html',
    tags JSONB DEFAULT '[]',
    file_path TEXT,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alerts Table (For report-svc)
CREATE TABLE IF NOT EXISTS alerts (
    id VARCHAR(100) PRIMARY KEY,
    rule_id VARCHAR(100) NOT NULL,
    device_id VARCHAR(100),
    type VARCHAR(20) NOT NULL,
    level VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'unresolved',
    data JSONB,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_devices_status ON devices(status);
CREATE INDEX IF NOT EXISTS ix_devices_model ON devices(model);
CREATE INDEX IF NOT EXISTS ix_devices_brand ON devices(brand);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_device_reservations_device_id ON device_reservations(device_id);
CREATE INDEX IF NOT EXISTS ix_device_reservations_user_id ON device_reservations(user_id);
CREATE INDEX IF NOT EXISTS ix_device_thresholds_device_id ON device_thresholds(device_id);

-- Insert sample admin (password: admin123)
INSERT INTO users (id, username, email, password_hash, display_name, role, status) VALUES
    ('admin-id', 'admin', 'admin@example.com', '$2b$12$JRPfP2Gn088pnmuuKnKFceuHE1tv7iqsk.OAXwt9q3H1GPcMzrNYi', 'Administrator', 'admin', 'active');
