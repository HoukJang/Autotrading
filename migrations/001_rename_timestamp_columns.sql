-- Migration: Rename confusing timestamp columns for better clarity
-- From: updated_at, last_updated
-- To: record_modified_at, market_data_refreshed_at

-- ==================================================
-- STEP 1: Add new columns with clear names
-- ==================================================

-- Add new columns to tickers table
ALTER TABLE tickers
ADD COLUMN IF NOT EXISTS record_modified_at TIMESTAMPTZ;

ALTER TABLE tickers
ADD COLUMN IF NOT EXISTS market_data_refreshed_at TIMESTAMPTZ;

-- ==================================================
-- STEP 2: Copy data from old columns to new columns
-- ==================================================

-- Copy data from old to new columns
UPDATE tickers
SET
    record_modified_at = updated_at,
    market_data_refreshed_at = last_updated
WHERE record_modified_at IS NULL OR market_data_refreshed_at IS NULL;

-- ==================================================
-- STEP 3: Update constraints and defaults
-- ==================================================

-- Set NOT NULL constraint where appropriate
-- (record_modified_at should always have a value)
ALTER TABLE tickers
ALTER COLUMN record_modified_at SET NOT NULL;

-- Set default for record_modified_at
ALTER TABLE tickers
ALTER COLUMN record_modified_at SET DEFAULT NOW();

-- ==================================================
-- STEP 4: Create indexes for new columns
-- ==================================================

-- Index for record modification queries
CREATE INDEX IF NOT EXISTS idx_tickers_record_modified_at
ON tickers (record_modified_at DESC);

-- Index for market data freshness queries
CREATE INDEX IF NOT EXISTS idx_tickers_market_data_refreshed_at
ON tickers (market_data_refreshed_at DESC NULLS LAST);

-- Combined index for batch processing priority
CREATE INDEX IF NOT EXISTS idx_tickers_data_freshness_priority
ON tickers (COALESCE(market_data_refreshed_at, created_at) ASC)
WHERE is_active = true;

-- ==================================================
-- VERIFICATION QUERIES
-- ==================================================

-- Verify data migration was successful
DO $$
BEGIN
    RAISE NOTICE 'Verifying data migration...';

    -- Check if any records have mismatched data
    IF EXISTS (
        SELECT 1 FROM tickers
        WHERE (updated_at IS NOT NULL AND record_modified_at IS NULL)
           OR (last_updated IS NOT NULL AND market_data_refreshed_at IS NULL)
    ) THEN
        RAISE EXCEPTION 'Data migration verification failed: Some records have NULL new columns but non-NULL old columns';
    END IF;

    RAISE NOTICE 'Data migration verification passed';
END $$;

-- ==================================================
-- CLEANUP: Drop old columns (MANUAL STEP)
-- ==================================================

-- IMPORTANT: Only run these after confirming application code is updated
-- and thoroughly tested with the new column names

-- DROP INDEX IF EXISTS idx_tickers_updated_at;
-- ALTER TABLE tickers DROP COLUMN IF EXISTS updated_at;
-- ALTER TABLE tickers DROP COLUMN IF EXISTS last_updated;

-- ==================================================
-- ROLLBACK SCRIPT (if needed)
-- ==================================================

/*
-- To rollback this migration:

-- Restore old columns
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE tickers ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ;

-- Copy data back
UPDATE tickers SET
    updated_at = record_modified_at,
    last_updated = market_data_refreshed_at;

-- Set constraints
ALTER TABLE tickers ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE tickers ALTER COLUMN updated_at SET DEFAULT NOW();

-- Drop new columns
DROP INDEX IF EXISTS idx_tickers_record_modified_at;
DROP INDEX IF EXISTS idx_tickers_market_data_refreshed_at;
DROP INDEX IF EXISTS idx_tickers_data_freshness_priority;
ALTER TABLE tickers DROP COLUMN IF EXISTS record_modified_at;
ALTER TABLE tickers DROP COLUMN IF EXISTS market_data_refreshed_at;
*/