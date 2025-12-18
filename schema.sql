-- schema.sql - Supabase PostgreSQL Database Schema

-- ===== CREATE SESSIONS TABLE =====
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    start_time TIMESTAMP WITH TIME ZONE, --DEFAULT CURRENT_TIMESTAMP
    updated_at TIMESTAMP WITH TIME ZONE, --DEFAULT CURRENT_TIMESTAMP
    end_time TIMESTAMP WITH TIME ZONE,
    summary TEXT,
    duration_seconds INTEGER,
    message_count INTEGER, --DEFAULT 0
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ===== CREATE SESSION_EVENTS TABLE =====
CREATE TABLE IF NOT EXISTS session_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('user_message', 'ai_response', 'function_call', 'tool_result')),
    content JSONB NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE, --DEFAULT CURRENT_TIMESTAMP
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ===== CREATE INDEXES FOR PERFORMANCE =====
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_end_time ON sessions(end_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_session_id ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON session_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON session_events(event_type);

-- ===== OPTIONAL: ENABLE ROW LEVEL SECURITY =====
-- ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE session_events ENABLE ROW LEVEL SECURITY;

-- ===== OPTIONAL: CREATE ANALYTICS VIEW =====
CREATE OR REPLACE VIEW session_analytics AS
SELECT 
    s.user_id,
    COUNT(DISTINCT s.session_id) as total_sessions,
    AVG(s.duration_seconds) as avg_duration_seconds,
    SUM(s.message_count) as total_messages,
    COUNT(DISTINCT DATE(s.start_time)) as days_active,
    MAX(s.start_time) as last_session
FROM sessions s
WHERE s.end_time IS NOT NULL
GROUP BY s.user_id
ORDER BY total_sessions DESC;
