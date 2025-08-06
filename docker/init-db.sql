-- Database initialization script for File Connector
-- This script sets up the initial database schema and configuration

-- Create extensions if they don't exist
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create database user if not exists (for additional permissions)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'connector_app') THEN
        CREATE ROLE connector_app WITH LOGIN PASSWORD 'connector_app_pass';
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE connector_db TO connector_app;
GRANT USAGE ON SCHEMA public TO connector_app;
GRANT CREATE ON SCHEMA public TO connector_app;

-- Create indexes for performance (will be created by SQLAlchemy but good to have)
-- Note: These will be created automatically by SQLAlchemy migrations, but included for reference

-- Commented out since SQLAlchemy will handle table creation
/*
-- Performance indexes for endpoints table
CREATE INDEX IF NOT EXISTS idx_endpoints_endpoint_type ON endpoints(endpoint_type);
CREATE INDEX IF NOT EXISTS idx_endpoints_is_active ON endpoints(is_active);
CREATE INDEX IF NOT EXISTS idx_endpoints_created_at ON endpoints(created_at);

-- Performance indexes for files table  
CREATE INDEX IF NOT EXISTS idx_files_external_id ON files(external_id);
CREATE INDEX IF NOT EXISTS idx_files_endpoint_id ON files(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at);
CREATE INDEX IF NOT EXISTS idx_files_updated_at ON files(updated_at);
CREATE INDEX IF NOT EXISTS idx_files_composite ON files(endpoint_id, updated_at);

-- Performance indexes for sync_logs table
CREATE INDEX IF NOT EXISTS idx_sync_logs_endpoint_id ON sync_logs(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_sync_started ON sync_logs(sync_started);
CREATE INDEX IF NOT EXISTS idx_sync_logs_sync_status ON sync_logs(sync_status);
*/

-- Create a function for updating updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Insert initial configuration data
INSERT INTO pg_stat_statements_info (dealloc) VALUES (0) ON CONFLICT DO NOTHING;

-- Create a health check function
CREATE OR REPLACE FUNCTION health_check()
RETURNS TEXT AS $$
BEGIN
    RETURN 'Database is healthy at ' || CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;