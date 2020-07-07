#!/usr/bin/env python2.5

import logging

import iplug
import wrappers

# TODO should we filter other virtual master devices out of the selection list?

################################################################################
class Plugin(iplug.ThreadedPlugin):

    devices = dict()

    #---------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        iplug.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.logger = logging.getLogger('Plugin.sprinklers')

    #---------------------------------------------------------------------------
    def validatePrefsConfigUi(self, values):
        errors = indigo.Dict()

        iplug.validateConfig_Int('threadLoopDelay', values, errors, min=60, max=3600)

        return ((len(errors) == 0), values, errors)

    #---------------------------------------------------------------------------
    def validateDeviceConfigUi(self, values, typeId, devId):
        errors = indigo.Dict()

        # TODO

        return ((len(errors) == 0), values, errors)

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
            obj.start(self)
            self.logger.info(u'"%s" -- device ready', device.name)

    #---------------------------------------------------------------------------
    def deviceStopComm(self, device):
        iplug.PluginBase.deviceStopComm(self, device)

        obj = self.devices.pop(device.id, None)
        if obj is not None: obj.stop()

    #---------------------------------------------------------------------------
    def runLoopStep(self):
        # devices are monitored for changes, but this is a catch-all just in case
        self._updateAllStatus()

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
            self.devices[device.id].turnZoneOn(zone)

    #---------------------------------------------------------------------------
    def _allZonesOff(self, device):
        self.devices[device.id].allZonesOff()

    #---------------------------------------------------------------------------
    def _updateAllStatus(self):
        self.logger.debug(u'update all devices')

        for device in indigo.devices.itervalues('self'):
            if device.enabled:
                self._updateStatus(device)
            else:
                self.logger.debug(u'Device disabled: %s', device.name)

    #---------------------------------------------------------------------------
    def _updateStatus(self, device):
        self.devices[device.id].updateStatus()

