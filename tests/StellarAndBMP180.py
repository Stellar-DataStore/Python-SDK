from StellarDS import StellarDS
from datetime import datetime
from ctypes import c_short
import smbus2
import time

DEVICE = 0x77
 
bus = smbus2.SMBus(1)
 
def convertToString(data):
    return str((data[1] + (256 * data[0])) / 1.2)

def getShort(data, index):
    return c_short((data[index] << 8) + data[index + 1]).value

def getUshort(data, index):
    return (data[index] << 8) + data[index + 1]

def readBmp180Id(addr=DEVICE):
    REG_ID = 0xD0
    (chipId, chipVersion) = bus.read_i2c_block_data(addr, REG_ID, 2)
    return (chipId, chipVersion)
  
def readBmp180(addr=DEVICE):
    REG_CALIB = 0xAA
    REG_MEAS = 0xF4
    REG_MSB = 0xF6
    REG_LSB = 0xF7
    CRV_TEMP = 0x2E
    CRV_PRES = 0x34 
    OVERSAMPLE = 3
    
    cal = bus.read_i2c_block_data(addr, REG_CALIB, 22)
    
    AC1 = getShort(cal, 0)
    AC2 = getShort(cal, 2)
    AC3 = getShort(cal, 4)
    AC4 = getUshort(cal, 6)
    AC5 = getUshort(cal, 8)
    AC6 = getUshort(cal, 10)
    B1 = getShort(cal, 12)
    B2 = getShort(cal, 14)
    MB = getShort(cal, 16)
    MC = getShort(cal, 18)
    MD = getShort(cal, 20)

    bus.write_byte_data(addr, REG_MEAS, CRV_TEMP)
    time.sleep(0.005)
    (msb, lsb) = bus.read_i2c_block_data(addr, REG_MSB, 2)
    UT = (msb << 8) + lsb

    bus.write_byte_data(addr, REG_MEAS, CRV_PRES + (OVERSAMPLE << 6))
    time.sleep(0.04)
    (msb, lsb, xsb) = bus.read_i2c_block_data(addr, REG_MSB, 3)
    UP = ((msb << 16) + (lsb << 8) + xsb) >> (8 - OVERSAMPLE)

    X1 = ((UT - AC6) * AC5) >> 15
    X2 = (MC << 11) / (X1 + MD)
    B5 = X1 + X2
    temperature = int(B5 + 8) >> 4

    B6 = B5 - 4000
    B62 = int(B6 * B6) >> 12
    X1 = (B2 * B62) >> 11
    X2 = int(AC2 * B6) >> 11
    X3 = X1 + X2
    B3 = (((AC1 * 4 + X3) << OVERSAMPLE) + 2) >> 2

    X1 = int(AC3 * B6) >> 13
    X2 = (B1 * B62) >> 16
    X3 = ((X1 + X2) + 2) >> 2
    B4 = (AC4 * (X3 + 32768)) >> 15
    B7 = (UP - B3) * (50000 >> OVERSAMPLE)

    P = (B7 * 2) / B4

    X1 = (int(P) >> 8) * (int(P) >> 8)
    X1 = (X1 * 3038) >> 16
    X2 = int(-7357 * P) >> 16
    pressure = int(P + ((X1 + X2 + 3791) >> 4))

    return (temperature/10.0,pressure/100.0)

PROJECT_ID = 'your_project_id'
CLIENT_ID = 'your_client_id'
CLIENT_SECRET = 'your_client_secret'
CALLBACK_URL = 'http://localhost:8080'
#Change to false if you want to use an access token instead of OAuth
oauth = True
#Change to false if you want to authenticate every time you run the script
persistent = True
ACCESS_TOKEN = 'your_access_token'

class SensorData:
    def __init__(self, chip_id, chip_version, temperature, pressure, measure_date):
        self.chip_id = chip_id
        self.chip_version = chip_version
        self.temperature = temperature
        self.pressure = pressure
        self.measure_date = measure_date

def read_sensor_data():
    chip_id, chip_version = readBmp180Id()
    temperature, pressure = readBmp180()
    measure_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return SensorData(chip_id, chip_version, temperature, pressure, measure_date)

def ensure_table_exists(stellar_ds):
    global table_id
    tables = stellar_ds.table.get(PROJECT_ID)
    if tables.status_code == 200 and tables.is_success:
        for data in tables.data:
            if "Sensor" in data.name:
                table_id = data.id
                return True
        table_data = Table('Sensor', 'Table with BMP180 sensor data', True)
        table_response = stellar_ds.table.add(PROJECT_ID, table_data)
        if table_response.status_code == 200 and table_response.is_success:
            print("\nTable created with:")
            print(f"ID: {table_response.data.id}")
            print(f"Name: {table_response.data.name}")
            print(f"Description: {table_response.data.description}")
            print(f"Multitenant: {table_response.data.is_multitenant}")
            table_id = table_response.data.id
            fields = [
                Field('chip_id', 'TinyInt'),
                Field('chip_version', 'TinyInt'),
                Field('temperature', 'Real'),
                Field('pressure', 'Real'),
                Field('measure_date', 'DateTime')
            ]
            for field_data in fields:
                field_add_response = stellar_ds.field.add(PROJECT_ID, table_response.data.id, field_data)
                if field_add_response.status_code == 200 and field_add_response.is_success:
                    print("\nField created with:")
                    print(f"ID: {field_add_response.data.id}")
                    print(f"Name: {field_add_response.data.name}")
                    print(f"Type: {field_add_response.data.type}")
            return True
        else:
            print_error_message(table_response)
    else:
        print_error_message(tables)
    return False

def print_error_message(response):
    print("\nFailed to proceed.")
    for message in response.messages:
        print(f"\nCode: {message.code}\nMessage: {message.message}")

def main():
    global table_id
    data_response = stellar_ds.data.add(PROJECT_ID, table_id, read_sensor_data())
    if data_response.status_code != 201 or not data_response.is_success:
        print_error_message(data_response)
    else:
        print("\nData added with:")
        print(f"Chip ID: {data_response.data[0].chip_id}")
        print(f"Chip Version: {data_response.data[0].chip_version}")
        print(f"ID: {data_response.data[0].id}")
        print(f"Temperature: {data_response.data[0].temperature}")
        print(f"Pressure: {data_response.data[0].pressure}")
        print(f"Measure Date: {data_response.data[0].measure_date}")
    time.sleep(10)

stellar_ds = StellarDS(is_oauth=oauth, is_persistent=persistent)
if oauth == False:
    stellar_ds.access_token(ACCESS_TOKEN)
else:
    stellar_ds.oauth(CLIENT_ID, CALLBACK_URL, CLIENT_SECRET)
ensure_table_exists(stellar_ds)

while __name__ == "__main__":
    main()
