#!/usr/bin/env python3
"""
PVS6 InfluxDB Logger

A clean, simple script to fetch data from a PVS6 system and write it to InfluxDB.
This script uses the varserver API to get all data and formats it according to the
InfluxDB structure shown in the user's examples.
"""

import time
import json
import base64
import logging
import requests
import urllib3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Suppress SSL warnings for PVS connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
INFLUX_URL = "http://127.0.0.1:8086/write"
INFLUX_DB = "pvs6_detail"
INFLUX_PRECISION = "s"  # seconds

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PVS6InfluxLogger:
    def __init__(self, pvs_host: str, influx_url: str = INFLUX_URL, influx_db: str = INFLUX_DB, verbose: bool = False, default_serial: str = None):
        self.pvs_host = pvs_host
        self.influx_url = influx_url
        self.influx_db = influx_db
        self.verbose = verbose
        self.default_serial = default_serial
        
        # Setup session
        self.session = requests.Session()
        self.session.verify = False  # Disable SSL verification for PVS

        # Default timeouts (connect, read) used for all network calls
        self.connect_timeout = 5
        self.read_timeout = 10
        self.request_timeout = (self.connect_timeout, self.read_timeout)
        
        # Authentication
        self.auth_token = None
        self.pvs_serial = None

    def authenticate(self) -> bool:
        """Authenticate with the PVS using basic auth."""
        try:
            # First, get the PVS serial number
            serial_response = self.session.get(
                f"https://{self.pvs_host}/vars?name=/sys/info/serialnum",
                timeout=self.request_timeout,
            )
            if serial_response.status_code != 200:
                logger.warning(f"Failed to get serial number: {serial_response.status_code}")
                if self.default_serial:
                    self.pvs_serial = self.default_serial
                    logger.info(f"Using default serial number: {self.pvs_serial}")
                else:
                    logger.error("No serial number found and no default serial provided")
                    return False
            else:
                serial_data = serial_response.json()
                if "values" in serial_data and len(serial_data["values"]) > 0:
                    self.pvs_serial = serial_data["values"][0]["value"]
                    logger.info(f"PVS Serial: {self.pvs_serial}")
                else:
                    logger.warning("No serial number found in response")
                    if self.default_serial:
                        self.pvs_serial = self.default_serial
                        logger.info(f"Using default serial number: {self.pvs_serial}")
                    else:
                        logger.error("No serial number found and no default serial provided")
                        return False

            # Create basic auth token using last 5 characters of serial
            password = self.pvs_serial[-5:] if self.pvs_serial else "F1084"
            auth_string = f"ssm_owner:{password}"
            auth_token = base64.b64encode(auth_string.encode()).decode()
            
            # Login to get session cookie
            login_url = f"https://{self.pvs_host}/auth?login"
            headers = {"Authorization": f"basic {auth_token}"}
            
            response = self.session.get(
                login_url,
                headers=headers,
                timeout=self.request_timeout,
            )
            if response.status_code == 200:
                data = response.json()
                if "session" in data:
                    self.auth_token = data["session"]
                    # Store the session cookie for subsequent requests
                    self.session.cookies.update(response.cookies)
                    logger.info("Successfully authenticated with PVS")
                    return True
                else:
                    logger.error(f"No session token in auth response: {data}")
                    return False
            else:
                logger.error(f"Authentication failed with status: {response.status_code}")
                return False
                    
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def get_all_data(self) -> Optional[Dict[str, Any]]:
        """Get all data from the PVS using the varserver API."""
        try:
            # Get all variables using the match parameter
            response = self.session.get(
                f"https://{self.pvs_host}/vars?match=/&fmt=obj",
                timeout=self.request_timeout,
            )
            if response.status_code != 200:
                logger.error(f"Failed to get data: {response.status_code}")
                return None
                
            data = response.json()
            logger.info(f"Retrieved {len(data)} variables from PVS")
            return data
            
        except Exception as e:
            logger.error(f"Error getting data: {e}")
            return None

    def escape_tag_value(self, value: str) -> str:
        """Escape tag values for InfluxDB."""
        if value is None:
            return ""
        s = str(value)
        s = s.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")
        return s

    def build_tags(self, tag_dict: Dict[str, str]) -> List[str]:
        """Build InfluxDB tag list, excluding empty values."""
        tags = []
        for key, value in tag_dict.items():
            if value and str(value).strip():  # Only include non-empty values
                tags.append(f"{key}={self.escape_tag_value(str(value))}")
        return tags

    def format_measurement_line(self, measurement: str, tags: List[str], fields: List[str], timestamp: int) -> str:
        """Format an InfluxDB measurement line with optional tags."""
        tag_part = f"{','.join(tags)}" if tags else ""
        tag_separator = "," if tags else ""
        return f"{measurement}{tag_separator}{tag_part} {','.join(fields)} {timestamp}"

    def escape_field_value(self, value: str) -> str:
        """Escape field values for InfluxDB."""
        if value is None or value == "":
            return None  # Return None for empty values, don't include them
        s = str(value)
        s = s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
        return f'"{s}"'

    def format_number(self, value: Any) -> Optional[float]:
        """Convert value to float, return None if not a number."""
        if value is None or value == "" or value == "nan":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def build_fields(self, data: Dict[str, Any]) -> List[str]:
        """Build InfluxDB field list from data dictionary, skipping None/empty values."""
        fields = []
        for key, value in data.items():
            if value is not None and value != "":
                if isinstance(value, str):
                    escaped_value = self.escape_field_value(value)
                    if escaped_value is not None:
                        fields.append(f'{key}={escaped_value}')
                else:
                    fields.append(f'{key}={value}')
        return fields

    def validate_influxdb_line(self, line: str) -> bool:
        """Validate a single InfluxDB line format."""
        try:
            # Basic format check: measurement[,tag_set] field_set [timestamp]
            parts = line.strip().split()
            if len(parts) < 2:
                return False
            
            # Check if it has measurement and fields
            measurement_part = parts[0]
            if ',' in measurement_part:
                # Has tags
                measurement, tags = measurement_part.split(',', 1)
            else:
                measurement = measurement_part
                tags = ""
            
            if not measurement:
                return False
                
            # Check fields (everything except last part if it's a timestamp)
            field_part = parts[1]
            if len(parts) > 2 and parts[-1].isdigit():
                # Has timestamp, fields are everything except last part
                field_part = ' '.join(parts[1:-1])
            
            if not field_part or '=' not in field_part:
                return False
                
            return True
        except Exception:
            return False

    def write_to_influxdb(self, lines: List[str]):
        """Write lines to InfluxDB."""
        if not lines:
            return
            
        # Validate lines before sending
        invalid_lines = []
        for i, line in enumerate(lines, 1):
            if not self.validate_influxdb_line(line):
                invalid_lines.append((i, line))
        
        if invalid_lines:
            logger.error(f"Found {len(invalid_lines)} invalid InfluxDB lines:")
            for line_num, line in invalid_lines:
                logger.error(f"  Line {line_num}: {line}")
            return
            
        # Print all records when verbose mode is enabled
        if self.verbose:
            print("\n" + "="*80)
            print("INFLUXDB RECORDS TO BE WRITTEN:")
            print("="*80)
            for i, line in enumerate(lines, 1):
                print(f"{i:2d}: {line}")
            print("="*80)
            print(f"Total records: {len(lines)}")
            print("="*80 + "\n")
            
        payload = "\n".join(lines)
        params = {"db": self.influx_db, "precision": INFLUX_PRECISION}
        
        try:
            response = self.session.post(
                self.influx_url,
                params=params,
                data=payload.encode("utf-8"),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            logger.info(f"Successfully wrote {len(lines)} lines to InfluxDB")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error writing to InfluxDB: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"InfluxDB response status: {e.response.status_code}")
                logger.error(f"InfluxDB response text: {e.response.text}")
            if self.verbose:
                logger.error(f"Payload that failed: {payload[:500]}...")  # Show first 500 chars
        except Exception as e:
            logger.error(f"Failed to write to InfluxDB: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"InfluxDB response: {e.response.text}")
            if self.verbose:
                logger.error(f"Payload that failed: {payload[:500]}...")  # Show first 500 chars

    def process_data(self, data: Dict[str, Any]) -> List[str]:
        """Process the raw data and convert to InfluxDB line format."""
        lines = []
        timestamp = int(time.time())
        
        # Process communication interface data
        # Create tags (interface, link, mode, ssid)
        comm_interface_tags = self.build_tags({
            "interface": data.get('/sys/info/active_interface', ''),
            "link": 'connected' if data.get('/net/sta0/state') == 'online' else 'disconnected',
            "mode": 'wan',
            "ssid": data.get('/sys/info/ssid', '')
        })
        
        # Create fields (numeric values only)
        comm_interface_fields = [
            f"internet={1 if data.get('/sys/toggle_cell/broadband_connected') == '1' else 0}",
            f"sms=0"
        ]
        
        lines.append(self.format_measurement_line("pvs_comm_interface", comm_interface_tags, comm_interface_fields, timestamp))
        
        # Process communication system data
        # Create tags (interface, interface_name)
        comm_system_tags = self.build_tags({
            "interface": data.get('/sys/info/active_interface', ''),
            "interface_name": data.get('/sys/info/active_interface', '')
        })
        
        # Create fields (numeric values only)
        comm_system_fields = [
            f"internet={1 if data.get('/sys/toggle_cell/broadband_connected') == '1' else 0}",
            f"sms={1 if data.get('/sys/toggle_cell/cell_connected') == '1' else 0}"
        ]
        
        lines.append(self.format_measurement_line("pvs_comm_system", comm_system_tags, comm_system_fields, timestamp))
        
        # Process device state data for meters
        meter_indices = set()
        for key in data.keys():
            if "/sys/devices/meter/" in key and "/" in key.split("/sys/devices/meter/")[1]:
                meter_idx = key.split("/sys/devices/meter/")[1].split("/")[0]
                meter_indices.add(meter_idx)
        
        for meter_idx in meter_indices:
            serial = data.get(f"/sys/devices/meter/{meter_idx}/sn", "")
            model = data.get(f"/sys/devices/meter/{meter_idx}/prodMdlNm", "")
            
            if serial and model:
                # Determine mode from model name (last letter: 'p' = production, 'c' = consumption)
                mode = "unknown"
                if model.lower().endswith('p'):
                    mode = "production"
                elif model.lower().endswith('c'):
                    mode = "consumption"
                
                # Create tags (device_type, model, serial)
                device_state_tags = self.build_tags({
                    "device_type": 'Power Meter',
                    "model": model,
                    "serial": serial
                })
                
                # Create fields (numeric values only)
                device_state_fields = ["state=1"]
                
                lines.append(self.format_measurement_line("pvs_device_state", device_state_tags, device_state_fields, timestamp))
        
        # Process device state data for inverters
        inverter_indices = set()
        for key in data.keys():
            if "/sys/devices/inverter/" in key and "/" in key.split("/sys/devices/inverter/")[1]:
                inverter_idx = key.split("/sys/devices/inverter/")[1].split("/")[0]
                inverter_indices.add(inverter_idx)
        
        for inverter_idx in inverter_indices:
            serial = data.get(f"/sys/devices/inverter/{inverter_idx}/sn", "")
            model = data.get(f"/sys/devices/inverter/{inverter_idx}/prodMdlNm", "")
            
            if serial and model:
                # Create tags (device_type, model, serial)
                device_state_tags = self.build_tags({
                    "device_type": 'Inverter',
                    "model": model,
                    "serial": serial
                })
                
                # Create fields (numeric values only)
                device_state_fields = ["state=1"]
                
                lines.append(self.format_measurement_line("pvs_device_state", device_state_tags, device_state_fields, timestamp))
        
        # Process grid profile data
        # Create tags (active_id, active_name, pending_id, pending_name, status, supported_by)
        grid_profile_tags = self.build_tags({
            "active_id": '0bbe89271171935e527489a181960fd15a3e9b5c',
            "active_name": 'IEEE-1547-2018 CA Rule21 v01.0',
            "pending_id": '0bbe89271171935e527489a181960fd15a3e9b5c',
            "pending_name": 'IEEE-1547-2018 CA Rule21 v01.0',
            "status": 'success',
            "supported_by": 'ALL'
        })
        
        # Create fields (numeric values only)
        grid_profile_fields = ["percent=100"]
        
        lines.append(self.format_measurement_line("pvs_grid_profile", grid_profile_tags, grid_profile_fields, timestamp))
        
        # Process inverter data
        for inverter_idx in inverter_indices:
            serial = data.get(f"/sys/devices/inverter/{inverter_idx}/sn", "")
            model = data.get(f"/sys/devices/inverter/{inverter_idx}/prodMdlNm", "")
            
            if serial and model:
                # Create tags (device_type, model, serial)
                tags = self.build_tags({
                    "device_type": 'Inverter',
                    "model": model,
                    "serial": serial
                })
                
                # Create fields (numeric values only)
                inverter_fields = []
                field_data = {
                    "freq_hz": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/freqHz")),
                    "i_3phsum_a": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/i3phsumA")),
                    "i_mppt1_a": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/iMppt1A")),
                    "ltea_3phsum_kwh": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/ltea3phsumKwh")),
                    "p_3phsum_kw": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/p3phsumKw")),
                    "p_mppt1_kw": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/pMppt1Kw")),
                    "t_htsnk_degc": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/tHtsnkDegc")),
                    "v_mppt1_v": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/vMppt1V")),
                    "vln_3phavg_v": self.format_number(data.get(f"/sys/devices/inverter/{inverter_idx}/vln3phavgV"))
                }
                
                for key, value in field_data.items():
                    if value is not None:
                        inverter_fields.append(f'{key}={value}')
                
                if inverter_fields:
                    lines.append(self.format_measurement_line("pvs_inverter", tags, inverter_fields, timestamp))
        
        # Process power meter data
        for meter_idx in meter_indices:
            serial = data.get(f"/sys/devices/meter/{meter_idx}/sn", "")
            model = data.get(f"/sys/devices/meter/{meter_idx}/prodMdlNm", "")
            
            if serial and model:
                # Determine mode from model name (last letter: 'p' = production, 'c' = consumption)
                mode = "unknown"
                if model.lower().endswith('p'):
                    mode = "production"
                elif model.lower().endswith('c'):
                    mode = "consumption"
                
                # Create tags (device_type, model, serial, mode)
                tags = self.build_tags({
                    "device_type": 'Power Meter',
                    "model": model,
                    "serial": serial,
                    "mode": mode
                })
                
                # Create fields (numeric values only)
                meter_fields = []
                field_data = {
                    "ct_scl_fctr": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/ctSclFctr")),
                    "freq_hz": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/freqHz")),
                    "i1_a": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/i1A")),
                    "i2_a": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/i2A")),
                    "neg_ltea_3phsum_kwh": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/negLtea3phsumKwh")),
                    "net_ltea_3phsum_kwh": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/netLtea3phsumKwh")),
                    "p_3phsum_kw": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/p3phsumKw")),
                    "pos_ltea_3phsum_kwh": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/posLtea3phsumKwh")),
                    "q_3phsum_kvar": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/q3phsumKvar")),
                    "s_3phsum_kva": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/s3phsumKva")),
                    "tot_pf_rto": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/totPfRto")),
                    "v12_v": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/v12V")),
                    "v1n_v": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/v1nV")),
                    "v2n_v": self.format_number(data.get(f"/sys/devices/meter/{meter_idx}/v2nV"))
                }
                
                for key, value in field_data.items():
                    if value is not None:
                        meter_fields.append(f'{key}={value}')
                
                if meter_fields:
                    lines.append(self.format_measurement_line("pvs_power_meter", tags, meter_fields, timestamp))
        
        # Process session start data
        # Create tags (model, serial, fwver, swver) - only include non-empty values
        fwrev = data.get('/sys/info/fwrev', '')
        fwver = fwrev.split(',')[0] if fwrev else ''
        
        session_start_tags = self.build_tags({
            "model": data.get('/sys/info/model', ''),
            "serial": data.get('/sys/info/serialnum', ''),
            "fwver": fwver,
            "swver": data.get('/sys/info/sw_rev', '')
        })
        
        # Create fields (numeric values only)
        session_start_fields = []
        field_data = {
            "build": self.format_number(data.get("/sys/info/build")),
            "easicver": self.format_number(data.get("/sys/info/easicver")),
            "ok": 1,
            "scbuild": self.format_number(data.get("/sys/info/scbuild")),
            "scver": self.format_number(data.get("/sys/info/scver")),
            "wnmodel": self.format_number(data.get("/sys/info/wnmodel")),
            "wnserial": self.format_number(data.get("/sys/info/wnserial")),
            "wnver": self.format_number(data.get("/sys/info/wnver"))
        }
        
        for key, value in field_data.items():
            if value is not None:
                session_start_fields.append(f'{key}={value}')
        
        if session_start_fields:
            lines.append(self.format_measurement_line("pvs_session_start", session_start_tags, session_start_fields, timestamp))
        
        # Process supervisor data
        # Create tags (device_type, model, serial)
        supervisor_tags = self.build_tags({
            "device_type": 'PVS',
            "model": 'PV Supervisor ' + data.get('/sys/info/model', ''),
            "serial": data.get('/sys/info/serialnum', '')
        })
        
        # Create fields (numeric values only)
        supervisor_fields = []
        field_data = {
            "dl_comm_err": self.format_number(data.get("/sys/info/dl_comm_err")),
            "dl_cpu_load": self.format_number(data.get("/sys/info/cpu_usage")),
            "dl_err_count": self.format_number(data.get("/sys/info/dl_err_count")),
            "dl_flash_avail": self.format_number(data.get("/sys/info/flash_usage")),
            "dl_mem_used": self.format_number(data.get("/sys/info/ram_usage")),
            "dl_scan_time": 10,  # Default value
            "dl_skipped_scans": 0,  # Default value
            "dl_untransmitted": 0,  # Default value
            "dl_uptime": self.format_number(data.get("/sys/info/uptime"))
        }
        
        for key, value in field_data.items():
            if value is not None:
                supervisor_fields.append(f'{key}={value}')
        
        if supervisor_fields:
            lines.append(self.format_measurement_line("pvs_supervisor", supervisor_tags, supervisor_fields, timestamp))
        
        return lines

    def run_once(self):
        """Run data collection once."""
        logger.info("Starting PVS6 data collection...")
        
        # Authenticate
        if not self.authenticate():
            logger.error("Authentication failed")
            return False
        
        # Get all data
        data = self.get_all_data()
        if not data:
            logger.error("Failed to get data from PVS")
            return False
        
        # Process data
        lines = self.process_data(data)
        if not lines:
            logger.error("No data to write")
            return False
        
        # Write to InfluxDB
        self.write_to_influxdb(lines)
        
        logger.info(f"Data collection completed - {len(lines)} lines written")
        return True

    def run_continuous(self, interval: int = 60):
        """Run data collection continuously."""
        logger.info(f"Starting continuous data collection (interval: {interval}s)")
        
        while True:
            try:
                self.run_once()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Stopping data collection...")
                break
            except Exception:
                logger.exception("Error in continuous run")
                time.sleep(interval)

    def test_influxdb_connection(self):
        """Test InfluxDB connection and database."""
        logger.info("Testing InfluxDB connection...")
        
        try:
            # Test 1: Ping InfluxDB
            ping_url = self.influx_url.replace("/write", "/ping")
            response = self.session.get(ping_url, timeout=5)
            if response.status_code == 204:
                logger.info("✓ InfluxDB is running")
            else:
                logger.error(f"✗ InfluxDB ping failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"✗ Cannot connect to InfluxDB: {e}")
            return False
        
        try:
            # Test 2: Check database
            query_url = self.influx_url.replace("/write", "/query")
            params = {"q": f"SHOW DATABASES"}
            response = self.session.get(query_url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                databases = []
                if "results" in data and len(data["results"]) > 0:
                    for series in data["results"][0].get("series", []):
                        if "values" in series:
                            databases.extend([row[0] for row in series["values"]])
                
                if self.influx_db in databases:
                    logger.info(f"✓ Database '{self.influx_db}' exists")
                else:
                    logger.warning(f"Database '{self.influx_db}' does not exist, creating...")
                    create_params = {"q": f"CREATE DATABASE {self.influx_db}"}
                    create_response = self.session.get(query_url, params=create_params, timeout=5)
                    if create_response.status_code == 200:
                        logger.info(f"✓ Database '{self.influx_db}' created")
                    else:
                        logger.error(f"✗ Failed to create database: {create_response.text}")
                        return False
            else:
                logger.error(f"✗ Failed to query databases: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"✗ Database check failed: {e}")
            return False
        
        try:
            # Test 3: Write test record
            test_line = f"test_measurement test_field=1 {int(time.time())}"
            params = {"db": self.influx_db, "precision": "s"}
            response = self.session.post(self.influx_url, params=params, data=test_line.encode("utf-8"), timeout=5)
            
            if response.status_code == 204:
                logger.info("✓ InfluxDB write test successful")
                return True
            else:
                logger.error(f"✗ InfluxDB write test failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"✗ InfluxDB write test failed: {e}")
            return False

    def test_single_line(self):
        """Test with a single InfluxDB line to isolate issues."""
        logger.info("Testing single InfluxDB line...")
        
        # Create a simple test line
        test_line = f"pvs_test_measurement test_field=1,test_string=\"hello\" {int(time.time())}"
        logger.info(f"Test line: {test_line}")
        
        try:
            params = {"db": self.influx_db, "precision": "s"}
            response = self.session.post(self.influx_url, params=params, data=test_line.encode("utf-8"), timeout=5)
            
            if response.status_code == 204:
                logger.info("✓ Single line test successful")
                return True
            else:
                logger.error(f"✗ Single line test failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"✗ Single line test failed: {e}")
            return False

    def test_real_data(self):
        """Test with real PVS data format."""
        logger.info("Testing with real PVS data format...")
        
        # Use sample data from the debug script
        sample_data = {
            "/sys/info/serialnum": "ZT231385000549F1084",
            "/sys/info/model": "PVS6",
            "/sys/info/active_interface": "sta0",
            "/sys/info/ssid": "SunPower13084",
            "/sys/toggle_cell/broadband_connected": "1",
            "/sys/toggle_cell/cell_connected": "0",
            "/net/sta0/state": "online",
            "/sys/devices/meter/0/sn": "PVS6M23131084p",
            "/sys/devices/meter/0/prodMdlNm": "PVS6M0400p",
            "/sys/devices/meter/0/ctSclFctr": "50",
            "/sys/devices/meter/0/freqHz": "59.992973",
            "/sys/devices/meter/0/p3phsumKw": "0.013776",
            "/sys/devices/inverter/0/sn": "E00122150014918",
            "/sys/devices/inverter/0/prodMdlNm": "AC_Module_Type_H",
            "/sys/devices/inverter/0/freqHz": "59.980000",
            "/sys/devices/inverter/0/p3phsumKw": "0.000265"
        }
        
        # Process the data
        lines = self.process_data(sample_data)
        logger.info(f"Generated {len(lines)} lines from sample data")
        
        # Test each line individually
        for i, line in enumerate(lines, 1):
            logger.info(f"Testing line {i}: {line[:100]}...")
            try:
                params = {"db": self.influx_db, "precision": "s"}
                response = self.session.post(self.influx_url, params=params, data=line.encode("utf-8"), timeout=5)
                
                if response.status_code == 204:
                    logger.info(f"✓ Line {i} successful")
                else:
                    logger.error(f"✗ Line {i} failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    logger.error(f"Line: {line}")
                    return False
            except Exception as e:
                logger.error(f"✗ Line {i} failed: {e}")
                logger.error(f"Line: {line}")
                return False
        
        logger.info("✓ All real data lines successful")
        return True


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PVS6 InfluxDB Logger")
    parser.add_argument("host", help="PVS6 hostname or IP address")
    parser.add_argument("--influx-url", default=INFLUX_URL, help="InfluxDB URL")
    parser.add_argument("--influx-db", default=INFLUX_DB, help="InfluxDB database name")
    parser.add_argument("--interval", type=int, default=60, help="Collection interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once instead of continuously")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--test-influxdb", action="store_true", help="Test InfluxDB connection and exit")
    parser.add_argument("--test-single-line", action="store_true", help="Test with a single InfluxDB line")
    parser.add_argument("--test-real-data", action="store_true", help="Test with real PVS data (no PVS connection needed)")
    parser.add_argument("--default-serial", help="Default serial number to use if retrieval fails")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger = PVS6InfluxLogger(args.host, args.influx_url, args.influx_db, args.verbose, args.default_serial)
    
    if args.test_influxdb:
        success = logger.test_influxdb_connection()
        exit(0 if success else 1)
    elif args.test_single_line:
        success = logger.test_single_line()
        exit(0 if success else 1)
    elif args.test_real_data:
        success = logger.test_real_data()
        exit(0 if success else 1)
    elif args.once:
        logger.run_once()
    else:
        logger.run_continuous(args.interval)


if __name__ == "__main__":
    main()
