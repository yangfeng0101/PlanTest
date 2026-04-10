-- 设备农场数据库初始化脚本
-- PostgreSQL 15

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 设备表
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(64) PRIMARY KEY,
    serial VARCHAR(64) UNIQUE NOT NULL,
    platform VARCHAR(16) NOT NULL CHECK (platform IN ('android', 'ios')),
    model VARCHAR(64),
    brand VARCHAR(32),
    os_version VARCHAR(32),
    screen_width INTEGER,
    screen_height INTEGER,
    status VARCHAR(16) DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'busy', 'maintenance')),
    owner_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 设备状态历史表
CREATE TABLE IF NOT EXISTS device_status_history (
    id VARCHAR(64) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    device_id VARCHAR(64) NOT NULL REFERENCES devices(id),
    status VARCHAR(16) NOT NULL,
    reason VARCHAR(256),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试脚本表
CREATE TABLE IF NOT EXISTS scripts (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    language VARCHAR(16) NOT NULL CHECK (language IN ('python', 'javascript', 'appium', 'airtest')),
    content TEXT,
    version INTEGER DEFAULT 1,
    description TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试任务表
CREATE TABLE IF NOT EXISTS test_tasks (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    script_id VARCHAR(64) REFERENCES scripts(id),
    device_id VARCHAR(64) REFERENCES devices(id),
    status VARCHAR(16) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    priority INTEGER DEFAULT 0,
    params JSONB,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试报告表
CREATE TABLE IF NOT EXISTS test_reports (
    id VARCHAR(64) PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL REFERENCES test_tasks(id),
    total_cases INTEGER DEFAULT 0,
    passed_cases INTEGER DEFAULT 0,
    failed_cases INTEGER DEFAULT 0,
    skipped_cases INTEGER DEFAULT 0,
    duration INTEGER, -- 秒
    video_url VARCHAR(512),
    log_url VARCHAR(512),
    report_url VARCHAR(512),
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试用例结果表
CREATE TABLE IF NOT EXISTS test_case_results (
    id VARCHAR(64) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    report_id VARCHAR(64) NOT NULL REFERENCES test_reports(id),
    case_name VARCHAR(256) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('passed', 'failed', 'skipped')),
    duration INTEGER, -- 毫秒
    error_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 投屏会话表
CREATE TABLE IF NOT EXISTS screen_sessions (
    id VARCHAR(64) PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL REFERENCES devices(id),
    user_id VARCHAR(64),
    webrtc_session_id VARCHAR(128),
    status VARCHAR(16) DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- 用户表 (简化版)
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(128) UNIQUE NOT NULL,
    display_name VARCHAR(128),
    role VARCHAR(16) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'viewer')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_platform ON devices(platform);
CREATE INDEX idx_devices_owner ON devices(owner_id);
CREATE INDEX idx_tasks_status ON test_tasks(status);
CREATE INDEX idx_tasks_device ON test_tasks(device_id);
CREATE INDEX idx_tasks_created ON test_tasks(created_at DESC);
CREATE INDEX idx_reports_task ON test_reports(task_id);
CREATE INDEX idx_case_results_report ON test_case_results(report_id);
CREATE INDEX idx_sessions_device ON screen_sessions(device_id);
CREATE INDEX idx_sessions_status ON screen_sessions(status);

-- 创建更新时间触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 应用触发器
CREATE TRIGGER update_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_scripts_updated_at BEFORE UPDATE ON scripts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 插入示例数据
INSERT INTO users (id, username, email, display_name, role) VALUES
    ('user-001', 'admin', 'admin@device-farm.local', 'Administrator', 'admin'),
    ('user-002', 'tester', 'tester@device-farm.local', 'Test User', 'user');

INSERT INTO devices (id, serial, platform, model, brand, os_version, screen_width, screen_height, status) VALUES
    ('device-001', 'ABC123456789', 'android', 'Pixel 6', 'Google', '13', 1080, 2400, 'online'),
    ('device-002', 'DEF987654321', 'android', 'Galaxy S22', 'Samsung', '13', 1080, 2340, 'online'),
    ('device-003', 'GHI456789123', 'ios', 'iPhone 14 Pro', 'Apple', '16.0', 1179, 2556, 'offline'),
    ('device-004', 'JKL789123456', 'ios', 'iPhone 13', 'Apple', '15.5', 1170, 2532, 'busy'),
    ('device-005', 'MNO123456789', 'android', 'OnePlus 11', 'OnePlus', '13', 1440, 3216, 'maintenance');

INSERT INTO scripts (id, name, language, content, version, description, created_by) VALUES
    ('script-001', 'Login Test', 'python', '# Python test script\nprint("Login test")', 1, 'Test user login flow', 'user-001'),
    ('script-002', 'Purchase Flow', 'javascript', '// JS test script\nconsole.log("Purchase test")', 1, 'Test purchase process', 'user-001');

INSERT INTO test_tasks (id, name, script_id, device_id, status, created_by) VALUES
    ('task-001', 'Login Test - Pixel 6', 'script-001', 'device-001', 'completed', 'user-002'),
    ('task-002', 'Purchase Flow - Galaxy S22', 'script-002', 'device-002', 'running', 'user-002'),
    ('task-003', 'Login Test - iPhone 13', 'script-001', 'device-004', 'pending', 'user-001');

INSERT INTO test_reports (id, task_id, total_cases, passed_cases, failed_cases, skipped_cases, duration, summary) VALUES
    ('report-001', 'task-001', 10, 8, 2, 0, 45, 'Most tests passed, 2 failures in edge cases');

INSERT INTO test_case_results (report_id, case_name, status, duration, error_message) VALUES
    ('report-001', 'test_login_valid', 'passed', 1200, NULL),
    ('report-001', 'test_login_invalid_password', 'passed', 800, NULL),
    ('report-001', 'test_login_empty_fields', 'passed', 500, NULL),
    ('report-001', 'test_logout', 'passed', 600, NULL),
    ('report-001', 'test_session_timeout', 'failed', 3000, 'Timeout exceeded'),
    ('report-001', 'test_remember_me', 'passed', 900, NULL),
    ('report-001', 'test_password_reset', 'passed', 1500, NULL),
    ('report-001', 'test_social_login', 'passed', 2000, NULL),
    ('report-001', 'test_two_factor_auth', 'failed', 5000, '2FA code not received'),
    ('report-001', 'test_account_lockout', 'passed', 1000, NULL);
