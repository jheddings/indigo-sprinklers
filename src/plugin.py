#!/usr/bin/env python2.5

import time
import copy

import iplug

# TODO should we filter other virtual master devices out of the selection list?
# TODO watch attached controllers to keep master devices status current

################################################################################
class Plugin(iplug.PluginBase):

    # used by master controllers to manage zone mappings
    MasterMap = dict()

    #---------------------------------------------------------------------------
    def deviceStartComm(self, device):
        iplug.PluginBase.deviceStartComm(self, device)

        typeId = device.deviceTypeId

        if typeId == 'MasterController':
            self._startDevice_MasterController(device)

    #---------------------------------------------------------------------------
    def deviceStopComm(self, device):
        iplug.PluginBase.deviceStopComm(self, device)

        typeId = device.deviceTypeId

        if typeId == 'MasterController':
            self.MasterMap.pop(device.id, None)

    #---------------------------------------------------------------------------
    # Sprinkler Control Action callback
    def actionControlSprinkler(self, action, device):
        self.logger.debug(u'sprinkler control -- %s : %s', device.name, action.sprinklerAction)

        ###### ZONE ON ######
        if action.sprinklerAction == indigo.kSprinklerAction.ZoneOn:
            zone = action.zoneIndex
            self._turnZoneOn(device, zone)

        ###### ALL ZONES OFF ######
        elif action.sprinklerAction == indigo.kSprinklerAction.AllZonesOff:
            self._allZonesOff(device)

    #---------------------------------------------------------------------------
    # General Action callback
    def actionControlUniversal(self, action, device):
        self.logger.debug(u'universal control -- %s : %s', device.name, action.deviceAction)

        ###### STATUS REQUEST ######
        if action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self._updateDevice(device)

    #---------------------------------------------------------------------------
    def _turnZoneOn(self, masterDevice, masterZoneId):
        self.logger.debug(u'turning on master zone %d -- %s', masterZoneId, masterDevice.name)

        # lookup the slave zone information from the master map
        zoneInfo = self._getZoneInfo(masterDevice, masterZoneId)
        self.logger.debug(u'found zone info in map: %s', zoneInfo)

        zoneName = zoneInfo['zoneName']
        zoneId = zoneInfo['zoneId']
        slaveId = zoneInfo['controllerId']

        if slaveId not in indigo.devices:
            self.logger.error(u'Device not found: %s', slaveId)
            self._setActiveZone(masterDevice, 0, 0, 0)
            return False

        slaveDevice = indigo.devices[slaveId]

        # check for an active program...
        if 'activeSlaveId' in masterDevice.states:
            activeSlaveId = masterDevice.states['activeSlaveId']
            self.logger.debug(u'active slave: %d', activeSlaveId)

            # if something is running, but it isn't on the same controller...
            if activeSlaveId is not 0 and activeSlaveId is not None:
                if activeSlaveId != slaveId:
                    indigo.sprinkler.stop(activeSlaveId)

        self.logger.debug(u'starting zone %s (%d) on slave: %s',
                          zoneName, zoneId, slaveDevice.name)

        indigo.sprinkler.setActiveZone(slaveDevice, index=zoneId)
        self._setActiveZone(masterDevice, masterZoneId, slaveId, zoneId)

        return True

    #---------------------------------------------------------------------------
    def _allZonesOff(self, masterDevice):
        self.logger.debug(u'turn off all zones on master: %s', masterDevice.name)
        zoneList = self.MasterMap[masterDevice.id]

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in zoneList }

        # stop watering on all slaves attched to this master
        for slaveId in slaves:

            controller = indigo.devices[slaveId]
            self.logger.debug(u'stopping zones on controller: %s', controller.name)

            indigo.sprinkler.stop(controller)

        self._setActiveZone(masterDevice, 0, 0, 0)

    #---------------------------------------------------------------------------
    def _setActiveZone(self, masterDevice, masterZone, slaveId=None, slaveZone=None):
        self.logger.debug(u'setting active zone status: %s [%d] => %s:%s',
                          masterDevice.name, masterZone, slaveId, slaveZone)

        masterDevice.updateStateOnServer('activeZone', masterZone)

        if slaveId is not None:
            masterDevice.updateStateOnServer('activeSlaveId', slaveId)

        if slaveZone is not None:
            masterDevice.updateStateOnServer('activeSlaveZone', slaveZone)

    #---------------------------------------------------------------------------
    def _startDevice_MasterController(self, device):

        # reset the master map for the controller device
        self.MasterMap[device.id] = list()

        controllers = device.pluginProps['controllers']

        if controllers is None or len(controllers) is 0:
            self.logger.warn(u'Nothing to do for device: %s', device.name)
            return

        # build the master map from all selected controllers
        for slaveId in controllers:
            slaveId = int(slaveId)

            # sometimes, devices get removed...
            if slaveId not in indigo.devices:
                self.logger.warn(u'Invalid controller: %s', slaveId)
                continue

            controller = indigo.devices[slaveId]

            if controller.enabled is False or controller.configured is False:
                self.logger.warn(u'Controller is not enabled: %s', controller.name)
                continue

            self.logger.debug(u'mapping slave controller: %s', controller.name)
            self._rebuildMasterMap(device, controller)

        # update device properties based on master map
        self._rebuildMasterDeviceProps(device)
        self.logger.info(u'Sprinkler device "%s" ready', device.name)

    #---------------------------------------------------------------------------
    def _rebuildMasterMap(self, masterDevice, slaveDevice):
        if masterDevice.id == slaveDevice.id:
            self.logger.warn(u'Circular device reference: %d', masterDevice.id)
            return

        # TODO remove current master map entries for slaveDevice.id

        for idx in range(slaveDevice.zoneCount):
            zoneName = slaveDevice.zoneNames[idx]
            maxDuration = slaveDevice.zoneMaxDurations[idx]
            zoneId = idx + 1

            zoneInfo = {
                'controllerId' : slaveDevice.id,
                'zoneName' : zoneName,
                'maxDuration' : maxDuration,
                'zoneId' : zoneId
            }

            self.logger.debug(u'adding to master map: %d => %s', masterDevice.id, zoneInfo)
            self.MasterMap[masterDevice.id].append(zoneInfo)

    #---------------------------------------------------------------------------
    def _rebuildMasterDeviceProps(self, device):
        zoneList = self.MasterMap[device.id]
        zoneNames = [info['zoneName'] for info in zoneList]
        durations = [str(info['maxDuration']) for info in zoneList]

        self.logger.debug(u'adding %d zones to %s', len(zoneList), device.name)

        # update inherited props for sprinkler devices
        props = device.pluginProps
        props["NumZones"] = len(zoneList)
        props["ZoneNames"] = ', '.join(zoneNames)
        props["MaxZoneDurations"] = ', '.join(durations)

        device.replacePluginPropsOnServer(props)

    #---------------------------------------------------------------------------
    def _getZoneInfo(self, masterDevice, masterZoneId):
        if masterDevice.id not in self.MasterMap:
            self.logger.error('Master controller not found in map: %d', masterDevice.id)
            return None

        zoneList = self.MasterMap[masterDevice.id]

        # zone numbers are 1-based, but our map starts at 0
        masterZoneIndex = masterZoneId - 1

        if masterZoneIndex >= len(zoneList):
            return None

        return zoneList[masterZoneIndex]

    #---------------------------------------------------------------------------
    def _getMasterZoneNumber(self, masterDevice, slaveDevice, slaveZoneNumber=None):
        if slaveZoneNumber is None:
            slaveZoneNumber = slaveDevice.activeZone

        if slaveZoneNumber is 0 or slaveZoneNumber is None:
            return 0

        if masterDevice.id not in self.MasterMap:
            self.logger.error('Master controller not found in map: %d', masterDevice.id)
            return None

        # find the slave zone ID in the master map
        zoneList = self.MasterMap[masterDevice.id]
        for masterZoneIndex in range(len(zoneList)):
            zoneInfo = zoneList[masterZoneIndex]

            if zoneInfo['controllerId'] == slaveDevice.id:
                if zoneInfo['zoneId'] == slaveZoneNumber:
                    return masterZoneIndex + 1

        return None

    #---------------------------------------------------------------------------
    def _updateDevice(self, device):
        self.logger.debug(u'update status for device: %s', device.name)

        typeId = device.deviceTypeId

        if typeId == 'MasterController':
            self._updateDevice_MasterController(device)

    #---------------------------------------------------------------------------
    def _updateDevice_MasterController(self, masterDevice):
        self.logger.debug(u'update status on master device: %s', masterDevice.name)
        zoneList = self.MasterMap[masterDevice.id]

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in zoneList }

        activeMasterZone = 0
        activeSlaveId = 0
        activeSlaveZone = 0

        # look for the active zone on associated controllers
        for slaveId in slaves:

            if slaveId not in indigo.devices:
                self.logger.warn(u'Controller not found: %d', contollerId)

            else:

                # get the active zone on the slave controller
                slaveDevice = indigo.devices[slaveId]
                slaveZoneNumber = slaveDevice.activeZone
                self.logger.debug(u'active zone on slave: %s -- %s', slaveDevice.name, slaveZoneNumber)

                # TODO we should check if there are multiple active zones

                if slaveZoneNumber is not None and slaveZoneNumber is not 0:
                    activeSlaveId = slaveId
                    activeSlaveZone = slaveZoneNumber
                    activeMasterZone = self._getMasterZoneNumber(masterDevice, slaveDevice)

        self._setActiveZone(masterDevice, activeMasterZone, activeSlaveId, activeSlaveZone)

