-- InfluxDB setup commands for PVS6 data
-- Run these commands in the InfluxDB CLI or web interface

-- Create the database
CREATE DATABASE pvs6_detail

-- Set retention policy (optional - keeps data for 1 year)
CREATE RETENTION POLICY "one_year" ON "pvs6_detail" DURATION 365d REPLICATION 1 DEFAULT

-- Alternative: Set retention policy to keep data forever (be careful with disk space)
-- CREATE RETENTION POLICY "forever" ON "pvs6_detail" DURATION 0s REPLICATION 1 DEFAULT

-- Show databases to verify
SHOW DATABASES

-- Show retention policies
SHOW RETENTION POLICIES ON pvs6_detail

-- Example queries to test data (run after some data has been collected):

-- Show all measurements
SHOW MEASUREMENTS

-- Get recent data from all measurements
SELECT * FROM pvs_inverter ORDER BY time DESC LIMIT 10
SELECT * FROM pvs_power_meter ORDER BY time DESC LIMIT 10
SELECT * FROM pvs_supervisor ORDER BY time DESC LIMIT 10

-- Get current power production
SELECT last(p_3phsum_kw) as current_power_kw FROM pvs_inverter WHERE time >= now() - 1h

-- Get daily energy production
SELECT sum(ltea_3phsum_kwh) as daily_energy_kwh FROM pvs_inverter WHERE time >= now() - 1d GROUP BY time(1h)
