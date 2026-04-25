-- Device Farm Database Initialization Script (Phase 3 aligned)
-- PostgreSQL 15

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum Types
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

-- Devices Table
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
    status VARCHAR(20) DEFAULT 'draft',
    tags JSONB DEFAULT '[]',
    file_path VARCHAR(500),
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Test Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(100) PRIMARY KEY,
    script_id VARCHAR(100) REFERENCES scripts(id),
    device_id VARCHAR(100),
    device_platform VARCHAR(20) DEFAULT 'android',
    device_capabilities JSONB DEFAULT '{}',
    parameters JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',
    result JSONB,
    error TEXT,
    log_file VARCHAR(500),
    report_id VARCHAR(100),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task Logs Table
CREATE TABLE IF NOT EXISTS task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    level VARCHAR(10) DEFAULT 'INFO' NOT NULL,
    message TEXT NOT NULL
);

-- Screenshots Table
CREATE TABLE IF NOT EXISTS screenshots (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    object_name VARCHAR(500) NOT NULL,
    url VARCHAR(1000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Videos Table
CREATE TABLE IF NOT EXISTS videos (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    object_name VARCHAR(500) NOT NULL,
    url VARCHAR(1000),
    duration FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Schedules Table
CREATE TABLE IF NOT EXISTS schedules (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    task VARCHAR(255) NOT NULL,
    schedule_type VARCHAR(20) NOT NULL,
    minute VARCHAR(10),
    hour VARCHAR(10),
    day_of_month VARCHAR(10),
    month_of_year VARCHAR(10),
    day_of_week VARCHAR(10),
    interval_every INTEGER,
    interval_unit VARCHAR(20),
    run_at TIMESTAMP,
    executed BOOLEAN DEFAULT FALSE,
    args JSONB DEFAULT '[]',
    kwargs JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    description TEXT,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    total_run_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Parallel Tasks Table
CREATE TABLE IF NOT EXISTS parallel_tasks (
    id VARCHAR(100) PRIMARY KEY,
    script_id VARCHAR(100) NOT NULL REFERENCES scripts(id),
    status VARCHAR(20) NOT NULL,
    selection_strategy VARCHAR(50) NOT NULL,
    max_concurrency INTEGER DEFAULT 1,
    parameters JSONB DEFAULT '{}',
    device_capabilities JSONB DEFAULT '{}',
    sub_tasks JSONB DEFAULT '[]',
    total_devices INTEGER DEFAULT 0,
    completed_devices INTEGER DEFAULT 0,
    failed_devices INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

-- Alert Rules Table
CREATE TABLE IF NOT EXISTS alert_rules (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    threshold FLOAT DEFAULT 0.0,
    duration_seconds INTEGER DEFAULT 300,
    channels_json TEXT DEFAULT '[]',
    recipients_json TEXT DEFAULT '[]',
    cooldown_seconds INTEGER DEFAULT 300,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    id VARCHAR(100) PRIMARY KEY,
    rule_id VARCHAR(100) NOT NULL REFERENCES alert_rules(id),
    rule_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    device_id VARCHAR(100),
    task_id VARCHAR(100),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100),
    notifications_sent INTEGER DEFAULT 0,
    last_notification_at TIMESTAMP
);

-- Alert History Table
CREATE TABLE IF NOT EXISTS alert_history (
    id VARCHAR(100) PRIMARY KEY,
    alert_id VARCHAR(100) NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(100),
    details_json TEXT DEFAULT '{}'
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

-- Indexes
CREATE INDEX IF NOT EXISTS ix_devices_status ON devices(status);
CREATE INDEX IF NOT EXISTS ix_devices_model ON devices(model);
CREATE INDEX IF NOT EXISTS ix_devices_brand ON devices(brand);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_device_reservations_device_id ON device_reservations(device_id);
CREATE INDEX IF NOT EXISTS ix_device_reservations_user_id ON device_reservations(user_id);
CREATE INDEX IF NOT EXISTS ix_device_thresholds_device_id ON device_thresholds(device_id);
CREATE INDEX IF NOT EXISTS ix_alert_rules_name ON alert_rules(name);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS ix_alerts_triggered_at ON alerts(triggered_at);

-- Insert sample admin (password: admin123)
INSERT INTO users (id, username, email, password_hash, display_name, role, status) VALUES
    ('admin-id', 'admin', 'admin@example.com', '$2b$12$JRPfP2Gn088pnmuuKnKFceuHE1tv7iqsk.OAXwt9q3H1GPcMzrNYi', 'Administrator', 'admin', 'active')
ON CONFLICT (id) DO NOTHING;

