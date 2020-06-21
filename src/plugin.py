#!/usr/bin/env python2.5

import time
import copy

import iplug

# TODO should we filter other virtual master devices out of the selection list?

################################################################################
class Plugin(iplug.ThreadedPlugin):

    # used by master controllers to manage zone mappings
    MasterMap = dict()

    #---------------------------------------------------------------------------
    def deviceStartComm(self, device):
        iplug.PluginBase.deviceStartComm(self, device)

        self.logger.debug('current props: %s', device.pluginProps)

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
    def runLoopStep(self): pass
    # TODO self._updateAllDevices()

    #---------------------------------------------------------------------------
    def loadPluginPrefs(self, prefs):
        iplug.PluginBase.loadPluginPrefs(self, prefs)

    #---------------------------------------------------------------------------
    # Sprinkler Control Action callback
    def actionControlSprinkler(self, action, device):
        self.logger.debug('sprinkler control -- %s : %s', device.name, action.sprinklerAction)

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
        self.logger.debug('universal control -- %s : %s', device.name, action.deviceAction)

        ###### STATUS REQUEST ######
        if action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self._updateStatus(device)

    #---------------------------------------------------------------------------
    def _turnZoneOn(self, master, masterZoneId):
        self.logger.debug('turning on master zone %d -- %s', masterZoneId, master.name)

        # lookup the slave zone information from the master map
        zoneInfo = self._getSlaveZoneInfo(master, masterZoneId)
        self.logger.debug('found zone info in map: %s', zoneInfo)

        zoneName = zoneInfo['zoneName']
        zoneId = zoneInfo['zoneId']
        slaveId = zoneInfo['controllerId']
        slave = indigo.devices[slaveId]

        # check for an active program...
        if 'activeSlaveId' in master.states:
            activeSlaveId = master.states['activeSlaveId']
            self.logger.debug('active slave: %d', activeSlaveId)

            # if something is running, but it isn't on the same controller...
            if activeSlaveId is not 0 and activeSlaveId is not None:
                if activeSlaveId != slaveId:
                    indigo.sprinkler.stop(activeSlaveId)

        self.logger.debug('starting zone %s (%d) on slave: %s',
                          zoneName, zoneId, slave.name)

        indigo.sprinkler.setActiveZone(slave, index=zoneId)

        master.updateStateOnServer("activeSlaveId", slaveId)
        master.updateStateOnServer("activeSlaveZone", zoneId)
        master.updateStateOnServer("activeZone", masterZoneId)

    #---------------------------------------------------------------------------
    def _allZonesOff(self, master):
        self.logger.debug('turn off all zones on master: %s', master.name)
        zoneList = self.MasterMap[master.id]

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in zoneList }

        # stop watering on all slaves attched to this master
        for slaveId in slaves:

            controller = indigo.devices[slaveId]
            self.logger.debug('stopping zones on controller: %s', controller.name)

            indigo.sprinkler.stop(controller)

            master.updateStateOnServer("activeZone", 0)
            master.updateStateOnServer("activeSlaveId", 0)
            master.updateStateOnServer("activeSlaveZone", 0)

    #---------------------------------------------------------------------------
    def _startDevice_MasterController(self, device):

        # reset the master map for the controller device
        self.MasterMap[device.id] = list()

        controllers = device.pluginProps['controllers']

        if controllers is None or len(controllers) is 0:
            self.logger.warn('Nothing to do for device: %s', device.name)
            return

        # build the master map from all selected controllers
        for slaveId in controllers:
            slaveId = int(slaveId)

            if slaveId not in indigo.devices:
                self.logger.warn('invalid slave controller: %s', slaveId)
                continue

            controller = indigo.devices[slaveId]

            if controller.enabled is False or controller.configured is False:
                self.logger.warn('Controller is not enabled: %s', controller.name)
                continue

            self.logger.debug('mapping controller: %s', controller.name)
            self._rebuildMasterMap(device, controller)

        # update device properties based on master map
        self._rebuildMasterDeviceProps(device)
        self.logger.info('Sprinkler device "%s" ready', device.name)

    #---------------------------------------------------------------------------
    def _rebuildMasterMap(self, master, slave):
        if master.id == slave.id:
            self.logger.warn('Circular device reference: %d', master.id)
            return

        # TODO remove current master map entries for slave.id

        for idx in range(slave.zoneCount):
            zoneName = slave.zoneNames[idx]
            maxDuration = slave.zoneMaxDurations[idx]
            zoneId = idx + 1

            zoneInfo = {
                'controllerId' : slave.id,
                'zoneName' : zoneName,
                'maxDuration' : maxDuration,
                'zoneId' : zoneId
            }

            self.logger.debug('adding to master map: %d => %s', master.id, zoneInfo)
            self.MasterMap[master.id].append(zoneInfo)

    #---------------------------------------------------------------------------
    def _rebuildMasterDeviceProps(self, device):
        zoneList = self.MasterMap[device.id]
        zoneNames = [info['zoneName'] for info in zoneList]
        durations = [str(info['maxDuration']) for info in zoneList]

        self.logger.debug('adding %d zones to %s', len(zoneList), device.name)

        # update inherited props for sprinkler devices
        props = device.pluginProps
        props["NumZones"] = len(zoneList)
        props["ZoneNames"] = ', '.join(zoneNames)
        props["MaxZoneDurations"] = ', '.join(durations)

        device.replacePluginPropsOnServer(props)

    #---------------------------------------------------------------------------
    def _getSlaveZoneInfo(self, master, masterZoneId):
        zoneList = self.MasterMap[master.id]

        # zone numbers are 1-based, but our map starts at 0
        masterZoneIndex = masterZoneId - 1

        return zoneList[masterZoneIndex]

    #---------------------------------------------------------------------------
    def _getMasterZoneNumber(self, master, slave, slaveZoneNumber=None):
        if slaveZoneNumber is None:
            slaveZoneNumber = slave.activeZone

        if slaveZoneNumber is 0 or slaveZoneNumber is None:
            return 0

        # find the slave zone ID in the master map
        zoneList = self.MasterMap[master.id]
        for masterZoneIndex in range(len(zoneList)):
            zoneInfo = zoneList[masterZoneIndex]

            if zoneInfo['controllerId'] == slave.id:
                if zoneInfo['zoneId'] == slaveZoneNumber:
                    return masterZoneIndex + 1

        return None

    #---------------------------------------------------------------------------
    def _updateStatus(self, device):
        self.logger.debug('update status for device: %s', device.name)

        typeId = device.deviceTypeId

        if typeId == 'MasterController':
            self._updateStatus_MasterController(device)

    #---------------------------------------------------------------------------
    def _updateStatus_MasterController(self, master):
        self.logger.debug('update status on master device: %s', master.name)
        zoneList = self.MasterMap[master.id]

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in zoneList }

        activeMasterZone = 0

        # look for the active zone on associated controllers
        for slaveId in slaves:

            if slaveId not in indigo.devices:
                self.logger.warn('Controller not found: %d', contollerId)

            else:

                # get the active zone on the slave controller
                slave = indigo.devices[slaveId]
                slaveZoneNumber = slave.activeZone
                self.logger.debug('active zone on slave: %s -- %s', slave.name, slaveZoneNumber)

                # TODO we should check if there are multiple active zones

                if slaveZoneNumber is not None and slaveZoneNumber is not 0:
                    master.updateStateOnServer("activeSlaveId", slaveId)
                    master.updateStateOnServer("activeSlaveZone", slaveZoneNumber)
                    activeMasterZone = self._getMasterZoneNumber(master, slave)

        master.updateStateOnServer("activeZone", activeMasterZone)

