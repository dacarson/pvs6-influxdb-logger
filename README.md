# PVS6 InfluxDB Logger

A clean, simple Python script to fetch data from a SunPower PVS6 (PV Supervisor) system and write it to InfluxDB. This script uses the varserver API to get all data and formats it according to InfluxDB line protocol.

## Features

- **Automatic Authentication**: Uses the PVS serial number to automatically authenticate
- **Fallback Serial Support**: Can use a default serial number if retrieval fails
- **Comprehensive Data Collection**: Retrieves data from all connected devices (inverters, meters, ESS, etc.)
- **InfluxDB Integration**: Directly writes to InfluxDB using line protocol
- **Robust Error Handling**: Graceful handling of network issues and missing data
- **Flexible Operation**: Run once or continuously with configurable intervals
- **Built-in Testing**: Test InfluxDB connection and data formatting

## API Reference

This logger uses the SunPower PVS6 varserver API to retrieve system data. For detailed information about the API endpoints and data structures, see the [pypvs GitHub repository](https://github.com/SunStrong-Management/pypvs).

## Requirements

- Python 3.6 or higher
- SunPower PVS6 with firmware build 61840 or later
- InfluxDB instance (tested with InfluxDB 1.x)
- Network access to both PVS6 and InfluxDB

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

```bash
python pvs6_influxdb_logger.py <pvs6_host>
```

### With Default Serial Number (Recommended)

If the PVS6 serial number retrieval fails, you can provide a fallback:

```bash
python pvs6_influxdb_logger.py <pvs6_host> --default-serial "ZT12345678901234567"
```

### Command Line Options

- `host`: PVS6 hostname or IP address (required)
- `--influx-url`: InfluxDB write URL (default: http://127.0.0.1:8086/write)
- `--influx-db`: InfluxDB database name (default: pvs6_detail)
- `--interval`: Collection interval in seconds (default: 60)
- `--once`: Run once instead of continuously
- `--verbose`: Enable verbose logging
- `--default-serial`: Default serial number to use if retrieval fails
- `--test-influxdb`: Test InfluxDB connection and exit
- `--test-single-line`: Test with a single InfluxDB line
- `--test-real-data`: Test with real PVS data (no PVS connection needed)

### Examples

**Run continuously with custom settings:**
```bash
python pvs6_influxdb_logger.py 192.168.1.100 \
  --influx-url http://influxdb.local:8086/write \
  --influx-db solar_data \
  --interval 30 \
  --default-serial "ZT12345678901234567"
```

**Run once for testing:**
```bash
python pvs6_influxdb_logger.py 192.168.1.100 --once --verbose
```

**Test InfluxDB connection:**
```bash
python pvs6_influxdb_logger.py 192.168.1.100 --test-influxdb
```

## Data Format

The logger writes data to InfluxDB in line protocol format with the following measurements:

### Measurements

- `pvs_session_start`: System information and session data
- `pvs_grid_profile`: Grid profile information
- `pvs_comm_interface`: Network interface status
- `pvs_comm_system`: System-level communication status
- `pvs_device_state`: Device state (working/not working)
- `pvs_supervisor`: PVS system metrics
- `pvs_inverter`: Inverter data
- `pvs_power_meter`: Power meter data

### Common Tags

- `serial`: Device serial number
- `device_type`: Type of device (PVS, Inverter, Power Meter, ESS)
- `model`: Device model
- `interface`: Network interface name
- `mode`: Meter mode (production/consumption)

## Authentication

The script automatically authenticates with the PVS6 using:
- Username: `ssm_owner`
- Password: Last 5 characters of the PVS serial number

If serial number retrieval fails, the script will use the provided `--default-serial` parameter, or fail gracefully if none is provided.

## Troubleshooting

### Connection Issues

If you get connection errors:
1. Verify the PVS IP address is correct
2. Ensure the PVS is running firmware build 61840 or later
3. Check that the PVS is accessible on the network
4. Verify InfluxDB is running and accessible

### Authentication Issues

The program automatically uses:
- Username: `ssm_owner`
- Password: Last 5 characters of the PVS serial number

If authentication fails:
1. Check that the PVS serial number is being detected correctly
2. Use the `--default-serial` parameter with the correct serial number
3. Verify the PVS6 is responding to API requests

### Data Issues

If data is not being written to InfluxDB:
1. Check InfluxDB is running: `python pvs6_influxdb_logger.py <host> --test-influxdb`
2. Verify the database exists
3. Check network connectivity to InfluxDB
4. Use `--verbose` flag to see detailed output
5. Test with sample data: `python pvs6_influxdb_logger.py <host> --test-real-data`

### Empty Tag Values

The script now automatically handles empty tag values that could cause InfluxDB parsing errors. Tags with empty values are excluded from the measurements.

## Configuration

### InfluxDB Setup

1. Create a database:
   ```sql
   CREATE DATABASE pvs6_detail
   ```

2. Optionally set retention policy:
   ```sql
   CREATE RETENTION POLICY "one_year" ON "pvs6_detail" DURATION 365d REPLICATION 1 DEFAULT
   ```

### Systemd Service (Linux)

Create `/etc/systemd/system/pvs6-logger.service`:

```ini
[Unit]
Description=PVS6 InfluxDB Logger
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pvs6-influxdb-logger
ExecStart=/usr/bin/python3 /home/pi/pvs6-influxdb-logger/pvs6_influxdb_logger.py 192.168.1.100 --default-serial "ZT12345678901234567"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable pvs6-logger
sudo systemctl start pvs6-logger
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review the verbose output with `--verbose` flag
3. Test individual components with the built-in test options
4. Create an issue with detailed logs and configuration
