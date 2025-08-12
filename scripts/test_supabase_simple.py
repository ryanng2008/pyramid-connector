#!/usr/bin/env python3
"""
Simple script to test Supabase connection without complex dependencies.
"""

import os
import sys
import asyncio
from pathlib import Path

# Simple logging
def log(message, level="INFO"):
    print(f"[{level}] {message}")

def test_supabase_direct():
    """Test Supabase connection directly."""
    try:
        from supabase import create_client
        
        # Get credentials from environment
        url = "https://ctlvrthcjusuvjjqtepe.supabase.co"
        key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bHZydGhjanVzdXZqanF0ZXBlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzc5NTEzOTcsImV4cCI6MjA1MzUyNzM5N30.ixwL95hxkCVMkNs04PusbThi_epjpvyqv_JCXgF7hTs"
        
        log(f"Testing connection to: {url}")
        
        # Create client
        supabase = create_client(url, key)
        
        # Test basic connection
        try:
            result = supabase.table("endpoints").select("id").limit(1).execute()
            log("✅ Connection successful!")
            log(f"Response: {result}")
            
            # Check if we have any data
            if result.data:
                log(f"Found {len(result.data)} endpoint(s)")
            else:
                log("No endpoints found (table might be empty)")
                
            return True
            
        except Exception as e:
            if "table" in str(e).lower() and "not" in str(e).lower():
                log("❌ Tables don't exist yet - need to create them")
                log("🔧 You'll need to run the table creation SQL in Supabase dashboard")
                return False
            else:
                log(f"❌ Connection error: {e}")
                return False
                
    except ImportError as e:
        log(f"❌ Import error: {e}")
        log("Make sure 'supabase' package is installed: pip install supabase")
        return False
    except Exception as e:
        log(f"❌ Unexpected error: {e}")
        return False

def print_table_sql():
    """Print SQL for creating tables."""
    sql = """
-- Create the tables in your Supabase SQL Editor:

-- 1. Create endpoints table
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

-- 2. Create files table
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

-- 3. Create sync_logs table
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

-- 4. Create indexes
CREATE INDEX IF NOT EXISTS idx_endpoints_endpoint_type ON endpoints(endpoint_type);
CREATE INDEX IF NOT EXISTS idx_endpoints_project_id ON endpoints(project_id);
CREATE INDEX IF NOT EXISTS idx_endpoints_user_id ON endpoints(user_id);
CREATE INDEX IF NOT EXISTS idx_files_endpoint_id ON files(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_files_external_file_id ON files(external_file_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_endpoint_id ON sync_logs(endpoint_id);

-- 5. Enable RLS (Row Level Security) - optional for now
-- ALTER TABLE endpoints ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE files ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

-- 6. Create basic policies (adjust based on your needs)
-- CREATE POLICY "Allow all operations" ON endpoints FOR ALL USING (true);
-- CREATE POLICY "Allow all operations" ON files FOR ALL USING (true);
-- CREATE POLICY "Allow all operations" ON sync_logs FOR ALL USING (true);
"""
    
    log("📋 TABLE CREATION SQL:")
    log("=" * 60)
    print(sql)
    log("=" * 60)
    log("Copy and paste this SQL into your Supabase SQL Editor")

def main():
    """Main function."""
    log("🚀 Supabase Connection Test")
    log("=" * 40)
    
    success = test_supabase_direct()
    
    if not success:
        log("\n📋 Next steps:")
        print_table_sql()
    else:
        log("✅ Supabase is ready to use!")

if __name__ == "__main__":
    main()
