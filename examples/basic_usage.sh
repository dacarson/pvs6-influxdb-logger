#!/bin/bash
# Basic usage examples for PVS6 InfluxDB Logger

# Example 1: Basic continuous logging
echo "Starting basic continuous logging..."
python pvs6_influxdb_logger.py 192.168.1.100

# Example 2: Run once with verbose output
echo "Running once with verbose output..."
python pvs6_influxdb_logger.py 192.168.1.100 --once --verbose

# Example 3: Custom InfluxDB settings
echo "Using custom InfluxDB settings..."
python pvs6_influxdb_logger.py 192.168.1.100 \
  --influx-url http://influxdb.local:8086/write \
  --influx-db solar_data \
  --interval 30

# Example 4: With default serial fallback
echo "Using default serial fallback..."
python pvs6_influxdb_logger.py 192.168.1.100 \
  --default-serial "ZT12345678901234567" \
  --verbose

# Example 5: Test InfluxDB connection
echo "Testing InfluxDB connection..."
python pvs6_influxdb_logger.py 192.168.1.100 --test-influxdb

# Example 6: Test with real data format
echo "Testing with real data format..."
python pvs6_influxdb_logger.py 192.168.1.100 --test-real-data
