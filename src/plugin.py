#!/usr/bin/env python2.5

import logging

import iplug
import wrappers

# TODO should we filter other virtual master devices out of the selection list?

################################################################################
class Plugin(iplug.PluginBase):

    devices = dict()

    #---------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        iplug.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.logger = logging.getLogger('Plugin.sprinklers')

    #---------------------------------------------------------------------------
    def deviceStartComm(self, device):
        iplug.PluginBase.deviceStartComm(self, device)

        obj = None

        # build a helper object for this device
        if device.deviceTypeId == 'TestController':
            obj = wrappers.TestController(device)
        elif device.deviceTypeId == 'MasterController':
            obj = wrappers.MasterController(device)

        # start the helper object
        if obj is not None:
            self.devices[device.id] = obj
            obj.start()
            self.logger.info(u'"%s" -- device ready', device.name)

    #---------------------------------------------------------------------------
    def deviceStopComm(self, device):
        iplug.PluginBase.deviceStopComm(self, device)

        obj = self.devices.pop(device.id, None)
        if obj is not None: obj.stop()

    #---------------------------------------------------------------------------
    # Sprinkler Control Action callback
    def actionControlSprinkler(self, action, device):
        self.logger.debug(u'sprinkler control -- %s : %s', device.name, action.sprinklerAction)

        ###### ZONE ON ######
        if action.sprinklerAction == indigo.kSprinklerAction.ZoneOn:
            self._turnZoneOn(device, action.zoneIndex)

        ###### ALL ZONES OFF ######
        elif action.sprinklerAction == indigo.kSprinklerAction.AllZonesOff:
            self._allZonesOff(device)

    #---------------------------------------------------------------------------
    # General Action callback
    def actionControlUniversal(self, action, device):
        self.logger.debug(u'universal control -- %s : %s', device.name, action.deviceAction)

        ###### STATUS REQUEST ######
        if action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self._updateStatus(device)

    #---------------------------------------------------------------------------
    def _turnZoneOn(self, device, zone):
        if zone is None or zone is 0:
            self._allZonesOff(device)

        else:
            obj = self.devices[device.id]
            obj.turnZoneOn(zone)

    #---------------------------------------------------------------------------
    def _allZonesOff(self, device):
        obj = self.devices[device.id]
        obj.allZonesOff()

    #---------------------------------------------------------------------------
    def _updateStatus(self, device):
        obj = self.devices[device.id]
        obj.updateStatus()

