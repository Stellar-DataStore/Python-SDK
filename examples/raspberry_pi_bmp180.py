"""Log BMP180 temperature and pressure readings from a Raspberry Pi to StellarDS.

    pip install stellards smbus2              # smbus2 only on the Pi
    export STELLARDS_TOKEN=...                # an access token with create/read rights on the table
    export STELLARDS_PROJECT=...
    python examples/raspberry_pi_bmp180.py --interval 60
    python examples/raspberry_pi_bmp180.py --simulate --count 3     # without a sensor

The script creates a "SensorReadings" table on first run. Wiring: BMP180 on I2C bus 1, address 0x77.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time
from ctypes import c_short
from decimal import Decimal
from typing import Any, Protocol

from stellards import FieldType, StellarDS, StellarDSError

TABLE_NAME = "SensorReadings"
BMP180_ADDRESS = 0x77


class Sensor(Protocol):
    chip_id: int

    def read(self) -> tuple[float, float]:
        """(temperature in °C, pressure in hPa)"""
        ...


class Bmp180:
    """The BMP180 over I2C, following the datasheet's compensation algorithm."""

    def __init__(self, bus_number: int = 1, address: int = BMP180_ADDRESS) -> None:
        import smbus2  # only needed on the Pi

        self.bus: Any = smbus2.SMBus(bus_number)
        self.address = address
        self.chip_id, _version = self.bus.read_i2c_block_data(address, 0xD0, 2)

    @staticmethod
    def _short(data: list[int], index: int) -> int:
        return int(c_short((data[index] << 8) + data[index + 1]).value)

    @staticmethod
    def _ushort(data: list[int], index: int) -> int:
        return (data[index] << 8) + data[index + 1]

    def read(self) -> tuple[float, float]:
        oversample = 3
        cal = self.bus.read_i2c_block_data(self.address, 0xAA, 22)
        ac1, ac2, ac3 = self._short(cal, 0), self._short(cal, 2), self._short(cal, 4)
        ac4, ac5, ac6 = self._ushort(cal, 6), self._ushort(cal, 8), self._ushort(cal, 10)
        b1, b2 = self._short(cal, 12), self._short(cal, 14)
        mc, md = self._short(cal, 18), self._short(cal, 20)

        self.bus.write_byte_data(self.address, 0xF4, 0x2E)
        time.sleep(0.005)
        msb, lsb = self.bus.read_i2c_block_data(self.address, 0xF6, 2)
        ut = (msb << 8) + lsb

        self.bus.write_byte_data(self.address, 0xF4, 0x34 + (oversample << 6))
        time.sleep(0.04)
        msb, lsb, xsb = self.bus.read_i2c_block_data(self.address, 0xF6, 3)
        up = ((msb << 16) + (lsb << 8) + xsb) >> (8 - oversample)

        x1 = ((ut - ac6) * ac5) >> 15
        x2 = (mc << 11) // (x1 + md)
        b5 = x1 + x2
        temperature = ((b5 + 8) >> 4) / 10.0

        b6 = b5 - 4000
        x1 = (b2 * ((b6 * b6) >> 12)) >> 11
        x2 = (ac2 * b6) >> 11
        x3 = x1 + x2
        b3 = (((ac1 * 4 + x3) << oversample) + 2) // 4
        x1 = (ac3 * b6) >> 13
        x2 = (b1 * ((b6 * b6) >> 12)) >> 16
        x3 = ((x1 + x2) + 2) >> 2
        b4 = (ac4 * (x3 + 32768)) >> 15
        b7 = (up - b3) * (50000 >> oversample)
        p = (b7 * 2) // b4 if b7 < 0x80000000 else (b7 // b4) * 2
        x1 = (p >> 8) * (p >> 8)
        x1 = (x1 * 3038) >> 16
        x2 = (-7357 * p) >> 16
        pressure = (p + ((x1 + x2 + 3791) >> 4)) / 100.0
        return temperature, pressure


class SimulatedSensor:
    chip_id = 0

    def read(self) -> tuple[float, float]:
        return round(random.uniform(18, 24), 1), round(random.uniform(1005, 1025), 2)


def ensure_table(sds: StellarDS) -> int:
    for table in sds.tables.list():
        if table.name == TABLE_NAME:
            return table.id
    table = sds.tables.create(TABLE_NAME, description="BMP180 readings from a Raspberry Pi")
    sds.fields.create(table.id, "chipId", FieldType.int())
    sds.fields.create(table.id, "temperature", FieldType.decimal(5, 1))
    sds.fields.create(table.id, "pressure", FieldType.decimal(7, 2))
    sds.fields.create(table.id, "measuredAt", FieldType.datetime_offset())
    print(f"Created table {TABLE_NAME} ({table.id})")
    return table.id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between readings")
    parser.add_argument("--count", type=int, default=0, help="stop after this many readings (0 = forever)")
    parser.add_argument("--simulate", action="store_true", help="use random readings instead of the sensor")
    args = parser.parse_args()

    token, project = os.environ.get("STELLARDS_TOKEN"), os.environ.get("STELLARDS_PROJECT")
    if not token or not project:
        print("Set STELLARDS_TOKEN and STELLARDS_PROJECT first.", file=sys.stderr)
        return 2

    sensor: Sensor
    if args.simulate:
        sensor = SimulatedSensor()
    else:
        try:
            sensor = Bmp180()
        except (ImportError, OSError) as error:
            print(f"No BMP180 available ({error}); run with --simulate to test without one.", file=sys.stderr)
            return 1

    with StellarDS(token, project=project) as sds:
        table_id = ensure_table(sds)
        taken = 0
        while args.count == 0 or taken < args.count:
            temperature, pressure = sensor.read()
            reading = {
                "chipId": sensor.chip_id,
                "temperature": Decimal(str(temperature)),
                "pressure": Decimal(str(pressure)),
                "measuredAt": dt.datetime.now(dt.timezone.utc),
            }
            try:
                saved = sds.records.create(table_id, reading)
                print(f"#{saved.get('id')}: {temperature} °C, {pressure} hPa")
            except StellarDSError as error:
                # Keep logging through network hiccups; the next reading tries again.
                print(f"Could not save the reading: {error}", file=sys.stderr)
            taken += 1
            if args.count == 0 or taken < args.count:
                time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
