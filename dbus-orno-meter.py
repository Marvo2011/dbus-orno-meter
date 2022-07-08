#!/usr/bin/env python
 
"""
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.
Reading information from the Fronius Smart Meter via http REST API and puts the info on dbus.
"""
from gi.repository import GLib
#import gobject
import dbus
import platform
#import argparse
import struct
import logging
import sys
import os
import requests # for http GET
import configparser # for config/ini file
from client import ModbusClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService
from vedbus import VeDbusItemImport

class DbusDummyService(object):
  def __init__(self, servicename, deviceinstance, paths, productname='ORNO OR-WE-517', connection='Orno TCP-Modbus'):
    self._dbusservice = VeDbusService(servicename)
    self._paths = paths
 
    logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))
 
    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
    self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self._dbusservice.add_path('/Mgmt/Connection', connection)
 
    # Create the mandatory objects
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ProductId', 16)
    self._dbusservice.add_path('/DeviceType', 345) 
    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/FirmwareVersion', 0.1)
    self._dbusservice.add_path('/HardwareVersion', 0)
    self._dbusservice.add_path('/Connected', 1)
    self._dbusservice.add_path('/Role', 'grid')

    _kwh = lambda p, v: (str(v) + 'kWh')
    _a = lambda p, v: (str(v) + 'A')
    _w = lambda p, v: (str(v) + 'W')
    _v = lambda p, v: (str(v) + 'V')

    service = self._dbusservice
    service.add_path('/Ac/Energy/Forward', None, gettextcallback=_kwh)
    service.add_path('/Ac/Energy/Reverse', None, gettextcallback=_kwh)
    service.add_path('/Ac/L1/Current', None, gettextcallback=_a)
    service.add_path('/Ac/L1/Energy/Forward', None, gettextcallback=_kwh)
    service.add_path('/Ac/L1/Energy/Reverse', None, gettextcallback=_kwh)
    service.add_path('/Ac/L1/Power', None, gettextcallback=_w)
    service.add_path('/Ac/L1/Voltage', None, gettextcallback=_v)
    service.add_path('/Ac/L2/Current', None, gettextcallback=_a)
    service.add_path('/Ac/L2/Energy/Forward', None, gettextcallback=_kwh)
    service.add_path('/Ac/L2/Energy/Reverse', None, gettextcallback=_kwh)
    service.add_path('/Ac/L2/Power', None, gettextcallback=_w)
    service.add_path('/Ac/L2/Voltage', None, gettextcallback=_v)
    service.add_path('/Ac/L3/Current', None, gettextcallback=_a)
    service.add_path('/Ac/L3/Energy/Forward', None, gettextcallback=_kwh)
    service.add_path('/Ac/L3/Energy/Reverse', None, gettextcallback=_kwh)
    service.add_path('/Ac/L3/Power', None, gettextcallback=_w)
    service.add_path('/Ac/L3/Voltage', None, gettextcallback=_v)
    service.add_path('/Ac/Power', None, gettextcallback=_w)
 
    for path, settings in self._paths.items():
      self._dbusservice.add_path(
        path, settings['initial'], writeable=True, onchangecallback=self._handlechangedvalue)
 
    # Here you must set your orno Modbus settings!
    self._modbus = ModbusClient(host='192.168.0.212', port=501, auto_open=True, unit_id=2, debug=True)

    GLib.timeout_add(5000, self._update) # pause 5s before the next request
 
  def _update(self):
    try:
      bus = dbus.SystemBus()
      AcActiveInL1Power = bus.get_object('com.victronenergy.vebus.ttyUSB2', '/Ac/ActiveIn/L1/P').GetValue()
      logging.debug("dbus response from /Ac/ActiveIn/L1/P: %s" % (AcActiveInL1Power));
      self._dbusservice['/Ac/Power'] = int(self._getBEFloat(0x001C)*1000) + int(AcActiveInL1Power)
      self._dbusservice['/Ac/L1/Power'] = int(self._getBEFloat(0x001E)*1000) + int(AcActiveInL1Power)
    except:
      self._dbusservice['/Ac/Power'] = int(self._getBEFloat(0x001C)*1000)
      self._dbusservice['/Ac/L1/Power'] = int(self._getBEFloat(0x001E)*1000)

    self._dbusservice['/Ac/L2/Power'] = int(self._getBEFloat(0x0020)*1000)
    self._dbusservice['/Ac/L3/Power'] = int(self._getBEFloat(0x0022)*1000)
    self._dbusservice['/Ac/L1/Current'] = float(format(float(self._getBEFloat(0x0016)), '.2f'))
    self._dbusservice['/Ac/L2/Current'] = float(format(float(self._getBEFloat(0x0018)), '.2f'))
    self._dbusservice['/Ac/L3/Current'] = float(format(float(self._getBEFloat(0x0022)), '.2f'))
    self._dbusservice['/Ac/L1/Voltage'] = int(self._getBEFloat(0x000E))
    self._dbusservice['/Ac/L2/Voltage'] = int(self._getBEFloat(0x0010))
    self._dbusservice['/Ac/L3/Voltage'] = int(self._getBEFloat(0x0012))
    self._dbusservice['/Ac/Energy/Forward'] = int(self._getBEFloat(0x0108))
    self._dbusservice['/Ac/L1/Energy/Forward'] = int(self._getBEFloat(0x010A))
    self._dbusservice['/Ac/L2/Energy/Forward'] = int(self._getBEFloat(0x010C))
    self._dbusservice['/Ac/L3/Energy/Forward'] = int(self._getBEFloat(0x010E))
    return True
 
  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change

  def _getBEFloat(self, reg):
    regs_l = self._modbus.read_holding_registers(reg, 2)
    if regs_l is not None:
      if len(regs_l) > 0:
        if regs_l[0] != 0 and regs_l[1] != 0:
          # print('debug: %s' % regs_l)
          dec = BinaryPayloadDecoder.fromRegisters(regs_l, byteorder=Endian.Big)
          return dec.decode_32bit_float()
        else:
          return False
      else:
        return False
    else:
      return False

def main():
  logging.basicConfig(level=logging.INFO)
 
  from dbus.mainloop.glib import DBusGMainLoop
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)
 
  pvac_output = DbusDummyService(
    servicename='com.victronenergy.grid.orno_30',
    deviceinstance=30, #meters from 30-34
    paths={}
  )
 
  logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
  mainloop = GLib.MainLoop()
  mainloop.run()
 
if __name__ == "__main__":
  main()
