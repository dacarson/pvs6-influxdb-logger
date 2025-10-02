# Configuration Examples

This document provides various configuration examples for different deployment scenarios.

## Environment Variables

You can use environment variables to configure the logger:

```bash
export PVS_HOST="192.168.1.100"
export PVS_DEFAULT_SERIAL="ZT12345678901234567"
export INFLUX_URL="http://influxdb.local:8086/write"
export INFLUX_DB="solar_data"
export COLLECTION_INTERVAL="30"

python pvs6_influxdb_logger.py $PVS_HOST \
  --default-serial $PVS_DEFAULT_SERIAL \
  --influx-url $INFLUX_URL \
  --influx-db $INFLUX_DB \
  --interval $COLLECTION_INTERVAL
```

## Docker Configuration

Create a `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pvs6_influxdb_logger.py .

CMD ["python", "pvs6_influxdb_logger.py", "192.168.1.100", "--default-serial", "ZT12345678901234567"]
```

Create a `docker-compose.yml`:

```yaml
version: '3.8'
services:
  pvs6-logger:
    build: .
    environment:
      - PVS_HOST=192.168.1.100
      - PVS_DEFAULT_SERIAL=ZT12345678901234567
      - INFLUX_URL=http://influxdb:8086/write
      - INFLUX_DB=solar_data
      - COLLECTION_INTERVAL=30
    restart: unless-stopped
    depends_on:
      - influxdb

  influxdb:
    image: influxdb:1.8
    ports:
      - "8086:8086"
    volumes:
      - influxdb-data:/var/lib/influxdb
    environment:
      - INFLUXDB_DB=solar_data

volumes:
  influxdb-data:
```

## Cron Job Configuration

For simple scheduling, use a cron job:

```bash
# Edit crontab
crontab -e

# Add this line to run every 5 minutes
*/5 * * * * /usr/bin/python3 /home/pi/pvs6-influxdb-logger/pvs6_influxdb_logger.py 192.168.1.100 --default-serial "ZT12345678901234567" --once >> /var/log/pvs6.log 2>&1
```

## Multiple PVS Systems

To monitor multiple PVS systems, create separate instances:

```bash
# PVS System 1
python pvs6_influxdb_logger.py 192.168.1.100 \
  --default-serial "ZT12345678901234567" \
  --influx-db "pvs1_data" &

# PVS System 2  
python pvs6_influxdb_logger.py 192.168.1.101 \
  --default-serial "ZT98765432109876543" \
  --influx-db "pvs2_data" &
```

## Log Rotation

Add log rotation for systemd service logs:

Create `/etc/logrotate.d/pvs6-logger`:

```
/var/log/pvs6.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 pi pi
    postrotate
        systemctl reload pvs6-logger
    endscript
}
```

## Network Configuration

For systems behind firewalls or with complex networking:

```bash
# Use specific network interface
python pvs6_influxdb_logger.py 192.168.1.100 \
  --default-serial "ZT12345678901234567" \
  --influx-url "http://10.0.0.100:8086/write"
```

## Troubleshooting Configuration

Enable maximum verbosity for debugging:

```bash
python pvs6_influxdb_logger.py 192.168.1.100 \
  --default-serial "ZT12345678901234567" \
  --verbose \
  --once
```

Test individual components:

```bash
# Test InfluxDB connection only
python pvs6_influxdb_logger.py 192.168.1.100 --test-influxdb

# Test data formatting only
python pvs6_influxdb_logger.py 192.168.1.100 --test-real-data

# Test single line format
python pvs6_influxdb_logger.py 192.168.1.100 --test-single-line
```
