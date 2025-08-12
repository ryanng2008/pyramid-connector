#!/usr/bin/env python3
"""
Script to set up Supabase tables and test connection.
Run this after configuring your Supabase credentials.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connector.database.supabase_service import init_supabase_service
from connector.config.settings import get_settings
from connector.utils.logging import get_logger

logger = get_logger(__name__)

# SQL to create tables in Supabase
CREATE_TABLES_SQL = """
-- Create endpoints table
CREATE TABLE IF NOT EXISTS endpoints (
    id SERIAL PRIMARY KEY,
    endpoint_type VARCHAR(50) NOT NULL,
    endpoint_details JSONB NOT NULL,
    project_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    schedule_cron VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    last_sync_at TIMESTAMP,
    last_sync_status VARCHAR(20) DEFAULT 'pending' NOT NULL
);

-- Create indexes for endpoints
CREATE INDEX IF NOT EXISTS idx_endpoints_endpoint_type ON endpoints(endpoint_type);
CREATE INDEX IF NOT EXISTS idx_endpoints_project_id ON endpoints(project_id);
CREATE INDEX IF NOT EXISTS idx_endpoints_user_id ON endpoints(user_id);

-- Create files table
CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL REFERENCES endpoints(id),
    external_file_id VARCHAR(255) NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    file_path TEXT,
    file_link TEXT NOT NULL,
    file_size INTEGER,
    file_type VARCHAR(100),
    external_created_at TIMESTAMP,
    external_updated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    last_synced_at TIMESTAMP DEFAULT NOW() NOT NULL,
    sync_status VARCHAR(20) DEFAULT 'completed' NOT NULL,
    file_metadata JSONB
);

-- Create indexes for files
CREATE INDEX IF NOT EXISTS idx_files_endpoint_id ON files(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_files_external_file_id ON files(external_file_id);

-- Create sync_logs table
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL REFERENCES endpoints(id),
    sync_started_at TIMESTAMP DEFAULT NOW() NOT NULL,
    sync_completed_at TIMESTAMP,
    sync_status VARCHAR(20) DEFAULT 'in_progress' NOT NULL,
    files_found INTEGER DEFAULT 0 NOT NULL,
    files_new INTEGER DEFAULT 0 NOT NULL,
    files_updated INTEGER DEFAULT 0 NOT NULL,
    files_skipped INTEGER DEFAULT 0 NOT NULL,
    files_error INTEGER DEFAULT 0 NOT NULL,
    error_message TEXT,
    error_details JSONB,
    execution_time_seconds INTEGER
);

-- Create indexes for sync_logs
CREATE INDEX IF NOT EXISTS idx_sync_logs_endpoint_id ON sync_logs(endpoint_id);

-- Create RLS policies (if needed)
-- Note: You may need to adjust these based on your authentication setup

-- Allow all operations for now (adjust based on your security requirements)
ALTER TABLE endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE files ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

-- Basic policies that allow all operations (you should customize these)
CREATE POLICY IF NOT EXISTS "Allow all operations on endpoints" 
    ON endpoints FOR ALL 
    USING (true)
    WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Allow all operations on files" 
    ON files FOR ALL 
    USING (true)
    WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Allow all operations on sync_logs" 
    ON sync_logs FOR ALL 
    USING (true)
    WITH CHECK (true);
"""


async def test_connection():
    """Test Supabase connection."""
    try:
        settings = get_settings()
        
        logger.info("Testing Supabase connection...")
        logger.info(f"Supabase URL: {settings.supabase.url}")
        logger.info(f"Anon Key configured: {'Yes' if settings.supabase.anon_key else 'No'}")
        
        # Initialize service
        service = await init_supabase_service()
        
        # Test connection
        connected = await service.test_connection()
        
        if connected:
            logger.info("✅ Supabase connection successful!")
            
            # Test table accessibility
            tables_ok = await service.create_tables_if_not_exist()
            if tables_ok:
                logger.info("✅ All required tables are accessible!")
            else:
                logger.error("❌ Some tables are not accessible. You may need to create them manually.")
                return False
                
        else:
            logger.error("❌ Supabase connection failed!")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Connection test failed: {str(e)}")
        return False


async def setup_tables():
    """Print SQL for creating tables."""
    logger.info("=== SUPABASE TABLE SETUP ===")
    logger.info("Copy and paste the following SQL into your Supabase SQL Editor:")
    logger.info("=" * 60)
    print(CREATE_TABLES_SQL)
    logger.info("=" * 60)
    logger.info("After running the SQL, run this script again to test the connection.")


async def main():
    """Main setup function."""
    settings = get_settings()
    
    logger.info("🚀 Supabase Setup Script")
    logger.info("=" * 40)
    
    if not settings.supabase.url:
        logger.error("❌ CONNECTOR_SUPABASE_URL not configured!")
        logger.error("Please set your Supabase URL in env.development or .env")
        return
    
    if not settings.supabase.anon_key:
        logger.error("❌ CONNECTOR_SUPABASE_ANON_KEY not configured!")
        logger.error("Please set your Supabase anon key in env.development or .env")
        return
    
    # Test connection first
    connected = await test_connection()
    
    if not connected:
        logger.info("\n📋 Table setup required")
        await setup_tables()
    else:
        logger.info("✅ Supabase is ready to use!")
        
        # Show some basic stats
        try:
            service = await init_supabase_service()
            endpoints = await service.get_active_endpoints()
            logger.info(f"📊 Active endpoints: {len(endpoints)}")
            
            if endpoints:
                for endpoint in endpoints:
                    files = await service.get_endpoint_files(endpoint.id, limit=100)
                    logger.info(f"   - {endpoint.endpoint_type} ({endpoint.project_id}): {len(files)} files")
        except Exception as e:
            logger.warning(f"Could not retrieve stats: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
