-- Remove unused column (never populated by the Shiny app)
ALTER TABLE preference
  DROP COLUMN IF EXISTS dining_preference;
