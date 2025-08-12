-- ========================================
-- IMPROVED SUPABASE SCHEMA - FLATTER DESIGN
-- ========================================
-- More normalized structure with less nesting for better performance and maintainability

-- ========================================
-- 1. ENDPOINTS TABLE (Main configuration)
-- ========================================

DROP TABLE IF EXISTS sync_logs CASCADE;
DROP TABLE IF EXISTS files CASCADE;
DROP TABLE IF EXISTS oauth_tokens CASCADE;
DROP TABLE IF EXISTS endpoints CASCADE;

CREATE TABLE endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Basic endpoint info
    name TEXT NOT NULL,
    endpoint_type TEXT NOT NULL CHECK (endpoint_type IN ('google_drive', 'autodesk_construction_cloud')),
    project_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    description TEXT,
    
    -- Status and control
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_sync_status TEXT NOT NULL DEFAULT 'pending' CHECK (last_sync_status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')),
    
    -- Scheduling (flattened from nested schedule_config)
    schedule_type TEXT NOT NULL DEFAULT 'interval' CHECK (schedule_type IN ('interval', 'cron', 'manual', 'webhook')),
    schedule_cron TEXT NOT NULL DEFAULT '*/5 * * * *',
    interval_minutes INTEGER DEFAULT 5 CHECK (interval_minutes > 0),
    
    -- File filtering (extracted from endpoint_details)
    file_types JSONB DEFAULT '["*"]',  -- Simple array: ["rvt", "dwg", "pdf"]
    max_files_per_sync INTEGER DEFAULT 1000 CHECK (max_files_per_sync > 0),
    max_file_size_mb INTEGER DEFAULT 100 CHECK (max_file_size_mb > 0),
    exclude_patterns JSONB DEFAULT '[]',  -- Simple array: ["*temp*", "*backup*"]
    
    -- Endpoint-specific config (simplified, non-auth data only)
    endpoint_config JSONB NOT NULL DEFAULT '{}',
    
    -- Metadata and timestamps
    tags JSONB DEFAULT '[]',  -- Simple array: ["engineering", "cad"]
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_sync_at TIMESTAMP,
    
    -- Indexes
    CONSTRAINT valid_schedule CHECK (
        (schedule_type = 'interval' AND interval_minutes IS NOT NULL) OR
        (schedule_type != 'interval')
    )
);

-- ========================================
-- 2. OAUTH_TOKENS TABLE (Separate table for auth)
-- ========================================

CREATE TABLE oauth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
    
    -- OAuth token data
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT DEFAULT 'Bearer',
    scope TEXT,
    
    -- Expiration tracking
    expires_in INTEGER DEFAULT 3600,
    expires_at TIMESTAMP NOT NULL,
    
    -- Audit trail
    obtained_at TIMESTAMP NOT NULL DEFAULT NOW(),
    refreshed_at TIMESTAMP,
    refresh_count INTEGER DEFAULT 0,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Ensure one active token per endpoint
    CONSTRAINT unique_active_token_per_endpoint UNIQUE (endpoint_id, is_active) DEFERRABLE INITIALLY DEFERRED
);

-- ========================================
-- 3. FILES TABLE (Unchanged, but cleaner references)
-- ========================================

CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
    
    -- File identification
    external_file_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT,
    file_link TEXT NOT NULL,
    
    -- File metadata
    file_size BIGINT,  -- Changed to BIGINT for large files
    file_type TEXT,
    mime_type TEXT,
    
    -- External timestamps
    external_created_at TIMESTAMP,
    external_updated_at TIMESTAMP,
    
    -- Internal tracking
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sync_status TEXT DEFAULT 'completed' CHECK (sync_status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
    
    -- Additional metadata (for extra fields not worth separate columns)
    file_metadata JSONB DEFAULT '{}',
    
    -- Constraints
    CONSTRAINT unique_file_per_endpoint UNIQUE (endpoint_id, external_file_id)
);

-- ========================================
-- 4. SYNC_LOGS TABLE (Enhanced with better metrics)
-- ========================================

CREATE TABLE sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
    
    -- Sync timing
    sync_started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sync_completed_at TIMESTAMP,
    execution_time_seconds INTEGER,
    
    -- Status
    sync_status TEXT NOT NULL DEFAULT 'in_progress' CHECK (sync_status IN ('in_progress', 'completed', 'failed', 'cancelled')),
    
    -- Results (flattened from nested stats)
    files_found INTEGER DEFAULT 0,
    files_new INTEGER DEFAULT 0,
    files_updated INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_error INTEGER DEFAULT 0,
    total_size_bytes BIGINT DEFAULT 0,
    
    -- Error tracking
    error_message TEXT,
    error_code TEXT,
    error_details JSONB DEFAULT '{}',
    
    -- Performance metrics
    api_calls_made INTEGER DEFAULT 0,
    rate_limit_hits INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0
);

-- ========================================
-- 5. INDEXES FOR PERFORMANCE
-- ========================================

-- Endpoints
CREATE INDEX idx_endpoints_type ON endpoints(endpoint_type);
CREATE INDEX idx_endpoints_user_id ON endpoints(user_id);
CREATE INDEX idx_endpoints_project_id ON endpoints(project_id);
CREATE INDEX idx_endpoints_enabled ON endpoints(enabled) WHERE enabled = true;
CREATE INDEX idx_endpoints_last_sync ON endpoints(last_sync_at);

-- OAuth tokens
CREATE INDEX idx_oauth_tokens_endpoint_id ON oauth_tokens(endpoint_id);
CREATE INDEX idx_oauth_tokens_expires_at ON oauth_tokens(expires_at);
CREATE INDEX idx_oauth_tokens_active ON oauth_tokens(is_active) WHERE is_active = true;

-- Files
CREATE INDEX idx_files_endpoint_id ON files(endpoint_id);
CREATE INDEX idx_files_external_id ON files(external_file_id);
CREATE INDEX idx_files_sync_status ON files(sync_status);
CREATE INDEX idx_files_updated ON files(external_updated_at);
CREATE INDEX idx_files_type ON files(file_type);

-- Sync logs
CREATE INDEX idx_sync_logs_endpoint_id ON sync_logs(endpoint_id);
CREATE INDEX idx_sync_logs_started_at ON sync_logs(sync_started_at);
CREATE INDEX idx_sync_logs_status ON sync_logs(sync_status);

-- ========================================
-- 6. ROW LEVEL SECURITY (RLS)
-- ========================================

ALTER TABLE endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE files ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

-- Endpoints policies
CREATE POLICY "Users can manage their own endpoints" 
ON endpoints FOR ALL 
USING (auth.uid() = user_id);

-- OAuth tokens policies (inherits from endpoints)
CREATE POLICY "Users can manage tokens for their endpoints" 
ON oauth_tokens FOR ALL 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = oauth_tokens.endpoint_id 
        AND auth.uid() = endpoints.user_id
    )
);

-- Files policies (inherits from endpoints)
CREATE POLICY "Users can access files from their endpoints" 
ON files FOR ALL 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND auth.uid() = endpoints.user_id
    )
);

-- Sync logs policies (inherits from endpoints)
CREATE POLICY "Users can view sync logs from their endpoints" 
ON sync_logs FOR ALL 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND auth.uid() = endpoints.user_id
    )
);

-- Service role bypass (for system operations)
CREATE POLICY "Service role full access endpoints" ON endpoints FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access oauth_tokens" ON oauth_tokens FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access files" ON files FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access sync_logs" ON sync_logs FOR ALL TO service_role USING (true);

-- ========================================
-- 7. EXAMPLE DATA
-- ========================================

-- Example Autodesk endpoint
INSERT INTO endpoints (
    name,
    endpoint_type,
    project_id,
    user_id,
    description,
    schedule_type,
    schedule_cron,
    interval_minutes,
    file_types,
    max_files_per_sync,
    exclude_patterns,
    endpoint_config,
    tags
) VALUES (
    'Project 0001 - Construction Files',
    'autodesk_construction_cloud',
    'project_0001',
    '550e8400-e29b-41d4-a716-446655440000',
    'Main Autodesk Construction Cloud endpoint for project files',
    'interval',
    '*/5 * * * *',
    5,
    '["rvt", "dwg", "ifc", "nwd", "pdf"]',
    1000,
    '["*temp*", "*backup*", "*~$*"]',
    '{
        "client_id": "your_client_id",
        "client_secret": "your_client_secret",
        "autodesk_project_id": "b.6c2cffb0-e8c8-43d3-b415-e53f4377cedb",
        "folder_id": null,
        "include_subfolders": true,
        "include_versions": true,
        "api_base_url": "https://developer.api.autodesk.com"
    }',
    '["construction", "bim", "project_0001"]'
);

-- Example OAuth token for the endpoint (using the endpoint UUID)
INSERT INTO oauth_tokens (
    endpoint_id,
    access_token,
    refresh_token,
    scope,
    expires_in,
    expires_at
) 
SELECT 
    e.id,
    'eyJhbGciOiJSUzI1NiIsImtpZCI6IkU2RjJGQUY5...',
    'AdskARIJ28cNlGFkBhXhQJ5YDOp_m7I4xKPjwprC...',
    'data:read data:write account:read',
    3599,
    NOW() + INTERVAL '1 hour'
FROM endpoints e 
WHERE e.project_id = 'project_0001' 
LIMIT 1;

-- ========================================
-- 8. HELPER FUNCTIONS
-- ========================================

-- Function to get active endpoints with valid tokens
CREATE OR REPLACE FUNCTION get_endpoints_with_valid_tokens()
RETURNS TABLE (
    endpoint_id UUID,
    endpoint_name TEXT,
    endpoint_type TEXT,
    project_id TEXT,
    has_valid_token BOOLEAN,
    token_expires_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.name,
        e.endpoint_type,
        e.project_id,
        (t.expires_at > NOW()) as has_valid_token,
        t.expires_at
    FROM endpoints e
    LEFT JOIN oauth_tokens t ON e.id = t.endpoint_id AND t.is_active = true
    WHERE e.enabled = true;
END;
$$ LANGUAGE plpgsql;

-- Function to update endpoint timestamps
CREATE OR REPLACE FUNCTION update_endpoint_sync_status(
    p_endpoint_id UUID,
    p_status TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE endpoints 
    SET 
        last_sync_status = p_status,
        last_sync_at = NOW(),
        updated_at = NOW()
    WHERE id = p_endpoint_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- 9. MIGRATION FROM OLD SCHEMA (if needed)
-- ========================================

/*
-- To migrate from the old nested structure:

INSERT INTO endpoints (
    name, endpoint_type, project_id, user_id, description,
    schedule_cron, file_types, max_files_per_sync,
    endpoint_config, enabled
)
SELECT 
    'Migrated Endpoint',
    endpoint_type,
    project_id,
    user_id,
    description,
    schedule_cron,
    COALESCE(endpoint_details->>'file_types', '["*"]')::jsonb,
    COALESCE((endpoint_details->>'max_files_per_sync')::integer, 1000),
    endpoint_details - 'oauth_tokens' - 'file_types' - 'max_files_per_sync',
    enabled
FROM old_endpoints_table;

-- Extract OAuth tokens separately
INSERT INTO oauth_tokens (endpoint_id, access_token, refresh_token, expires_at)
SELECT 
    new_endpoint_id,
    endpoint_details->'oauth_tokens'->>'access_token',
    endpoint_details->'oauth_tokens'->>'refresh_token',
    TO_TIMESTAMP((endpoint_details->'oauth_tokens'->>'expires_at')::bigint)
FROM old_endpoints_table
WHERE endpoint_details->'oauth_tokens' IS NOT NULL;
*/
