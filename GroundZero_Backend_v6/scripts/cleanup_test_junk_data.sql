-- Run this ONCE against your DEV database (not the new groundzero_test
-- database conftest.py now isolates tests onto). Removes the junk rows
-- test_full_admin_moderation_flow_through_the_http_api wrote into your
-- real DB every time you ran pytest before this fix. Safe to run more
-- than once — matches by the fixed name prefix the test itself uses, and
-- will simply affect 0 rows once already cleaned.

DELETE FROM community_submissions
WHERE submitted_place_json ->> 'name' LIKE 'HTTP Flow Test Kitchen %';

DELETE FROM places
WHERE name LIKE 'HTTP Flow Test Kitchen %';

-- Sanity check — should return 0 rows for both after the deletes above:
-- SELECT count(*) FROM places WHERE name LIKE 'HTTP Flow Test Kitchen %';
-- SELECT count(*) FROM community_submissions WHERE submitted_place_json ->> 'name' LIKE 'HTTP Flow Test Kitchen %';
