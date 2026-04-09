-- TravelDashboard: food text fields + structured checkbox tags on preference
-- Run after 001_app_user_preference.sql

ALTER TABLE preference
  ADD COLUMN IF NOT EXISTS food_like_text TEXT,
  ADD COLUMN IF NOT EXISTS food_dislike_text TEXT,
  ADD COLUMN IF NOT EXISTS food_tags JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN preference.food_like_text IS 'Free text; UI caps at 50 words';
COMMENT ON COLUMN preference.food_dislike_text IS 'Free text; UI caps at 50 words';
COMMENT ON COLUMN preference.food_tags IS 'JSON e.g. {"like":["street_food"],"dislike":["offal"],"dietary":["vegetarian"]}';
