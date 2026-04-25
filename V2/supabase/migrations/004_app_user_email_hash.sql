-- Deterministic identity for lookups (SHA-256 hex of normalized email in app; mirrors Python hashlib)
-- Run after 001–003.

ALTER TABLE app_user
  ADD COLUMN IF NOT EXISTS email_hash TEXT;

UPDATE app_user
SET email_hash = encode(
  digest(convert_to(lower(trim(email)), 'UTF8'), 'sha256'),
  'hex'
)
WHERE email_hash IS NULL AND email IS NOT NULL;

-- Unique only when present (allows legacy edge cases during transition)
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_user_email_hash ON app_user (email_hash)
  WHERE email_hash IS NOT NULL;

ALTER TABLE app_user
  ALTER COLUMN email_hash SET NOT NULL;

COMMENT ON COLUMN app_user.email_hash IS 'SHA-256 hex of lower(trim(email)); stable identity for returning user lookup';
