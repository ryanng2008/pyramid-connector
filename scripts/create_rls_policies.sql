-- ========================================
-- SUPABASE RLS POLICIES FOR FILE CONNECTOR
-- ========================================
-- Run this SQL in your Supabase SQL Editor to set up Row Level Security

-- ========================================
-- 1. ENABLE RLS ON ALL TABLES
-- ========================================

ALTER TABLE endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE files ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

-- ========================================
-- 2. ENDPOINTS TABLE POLICIES
-- ========================================

-- Policy: Users can only see their own endpoints
CREATE POLICY "Users can view their own endpoints" 
ON endpoints 
FOR SELECT 
USING (
    auth.uid()::text = user_id OR 
    auth.jwt() ->> 'email' = user_id
);

-- Policy: Users can insert endpoints for themselves
CREATE POLICY "Users can insert their own endpoints" 
ON endpoints 
FOR INSERT 
WITH CHECK (
    auth.uid()::text = user_id OR 
    auth.jwt() ->> 'email' = user_id
);

-- Policy: Users can update their own endpoints
CREATE POLICY "Users can update their own endpoints" 
ON endpoints 
FOR UPDATE 
USING (
    auth.uid()::text = user_id OR 
    auth.jwt() ->> 'email' = user_id
)
WITH CHECK (
    auth.uid()::text = user_id OR 
    auth.jwt() ->> 'email' = user_id
);

-- Policy: Users can delete their own endpoints
CREATE POLICY "Users can delete their own endpoints" 
ON endpoints 
FOR DELETE 
USING (
    auth.uid()::text = user_id OR 
    auth.jwt() ->> 'email' = user_id
);

-- ========================================
-- 3. FILES TABLE POLICIES (with JOIN)
-- ========================================

-- Policy: Users can view files from their endpoints
CREATE POLICY "Users can view files from their endpoints" 
ON files 
FOR SELECT 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can insert files to their endpoints
CREATE POLICY "Users can insert files to their endpoints" 
ON files 
FOR INSERT 
WITH CHECK (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can update files from their endpoints
CREATE POLICY "Users can update files from their endpoints" 
ON files 
FOR UPDATE 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can delete files from their endpoints
CREATE POLICY "Users can delete files from their endpoints" 
ON files 
FOR DELETE 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- ========================================
-- 4. SYNC_LOGS TABLE POLICIES (with JOIN)
-- ========================================

-- Policy: Users can view sync logs from their endpoints
CREATE POLICY "Users can view sync logs from their endpoints" 
ON sync_logs 
FOR SELECT 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can insert sync logs to their endpoints
CREATE POLICY "Users can insert sync logs to their endpoints" 
ON sync_logs 
FOR INSERT 
WITH CHECK (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can update sync logs from their endpoints
CREATE POLICY "Users can update sync logs from their endpoints" 
ON sync_logs 
FOR UPDATE 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- Policy: Users can delete sync logs from their endpoints
CREATE POLICY "Users can delete sync logs from their endpoints" 
ON sync_logs 
FOR DELETE 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = sync_logs.endpoint_id 
        AND (
            auth.uid()::text = endpoints.user_id OR 
            auth.jwt() ->> 'email' = endpoints.user_id
        )
    )
);

-- ========================================
-- 5. ALTERNATIVE: PROJECT-BASED ACCESS
-- ========================================
-- Uncomment these if you want project-based access instead of user-based

/*
-- Project-based policies (alternative approach)
CREATE POLICY "Users can view files from their projects" 
ON files 
FOR SELECT 
USING (
    EXISTS (
        SELECT 1 FROM endpoints 
        WHERE endpoints.id = files.endpoint_id 
        AND endpoints.project_id IN (
            SELECT project_id FROM endpoints 
            WHERE auth.uid()::text = user_id 
            OR auth.jwt() ->> 'email' = user_id
        )
    )
);
*/

-- ========================================
-- 6. SERVICE ROLE BYPASS (for backend operations)
-- ========================================

-- Allow service role to bypass RLS for system operations
CREATE POLICY "Service role has full access to endpoints" 
ON endpoints 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);

CREATE POLICY "Service role has full access to files" 
ON files 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);

CREATE POLICY "Service role has full access to sync_logs" 
ON sync_logs 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);

-- ========================================
-- 7. TESTING THE POLICIES
-- ========================================

-- Test queries you can run to verify the policies work:

/*
-- 1. Insert test endpoint (replace with your actual user ID/email)
INSERT INTO endpoints (endpoint_type, endpoint_details, project_id, user_id, schedule_cron) 
VALUES ('test', '{}', 'test_project', 'your_user_id_or_email', '0 0 * * *');

-- 2. Insert test file
INSERT INTO files (endpoint_id, external_file_id, file_name, file_link) 
VALUES (1, 'test_file_123', 'test.pdf', 'https://example.com/test.pdf');

-- 3. Try to query files (should only return files from your endpoints)
SELECT f.*, e.user_id 
FROM files f 
JOIN endpoints e ON f.endpoint_id = e.id;

-- 4. Try to query as different user (should return no results)
-- This would need to be tested with different authentication
*/
