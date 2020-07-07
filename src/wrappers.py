# helper classes for the Sprinkler Buddy plugin

import indigo
import logging

# TODO watch attached controllers to keep master devices status current
# XXX there are several duplicate code blocks, especially for error handling

################################################################################
class ControllerBase:
    device = None

    #---------------------------------------------------------------------------
    def __init__(self, device):
        self.logger = logging.getLogger('Plugin.sprinklers.ControllerBase')
        self.device = device

    #---------------------------------------------------------------------------
    def turnZoneOn(self, zone): pass

    #---------------------------------------------------------------------------
    def allZonesOff(self): pass

    #---------------------------------------------------------------------------
    def updateStatus(self): pass

    # FIXME start and stop are confusing, since they could refer to zones...

    #---------------------------------------------------------------------------
    def start(self, plugin): pass

    #---------------------------------------------------------------------------
    def stop(self): pass

################################################################################
class MasterController(ControllerBase):

    zoneInfoList = None

    #---------------------------------------------------------------------------
    def __init__(self, device):
        ControllerBase.__init__(self, device)

        self.logger = logging.getLogger('Plugin.sprinklers.MasterController')

    #---------------------------------------------------------------------------
    def turnZoneOn(self, masterZoneId):
        self.logger.debug(u'turning on master zone %d -- %s', masterZoneId, self.device.name)

        if masterZoneId > len(self.zoneInfoList):
            self.logger.error(u'No such zone: %d -- %s', masterZoneId, self.device.name)
            self._updateActiveDeviceStates(0, 0, 0)
            return False

        # zones are 1-based indexing, so subtract 1 for our list
        zoneInfo = self.zoneInfoList[masterZoneId-1]
        self.logger.debug(u'found zone info in map: %s', zoneInfo)

        zoneName = zoneInfo['zoneName']
        slaveZoneId = zoneInfo['zoneId']
        slaveDeviceId = zoneInfo['controllerId']

        if slaveDeviceId not in indigo.devices:
            self.logger.error(u'Device not found (may have been deleted): %s', slaveDeviceId)
            self._updateActiveDeviceStates(0, 0, 0)
            return False

        slaveDevice = indigo.devices[slaveDeviceId]

        self.logger.debug(u'starting zone %s (%d) on slave: %s',
                          zoneName, slaveZoneId, slaveDevice.name)

        self._prepForNextZone(slaveDeviceId, slaveZoneId)
        indigo.sprinkler.setActiveZone(slaveDevice, index=slaveZoneId)
        self._updateActiveDeviceStates(masterZoneId, slaveDeviceId, slaveZoneId)

        return True

    #---------------------------------------------------------------------------
    def allZonesOff(self):
        self.logger.debug(u'turn off all zones on master: %s', self.device.name)

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in self.zoneInfoList }

        # stop watering on all slaves attched to this master
        for slaveDeviceId in slaves:

            if slaveDeviceId not in indigo.devices:
                self.logger.warn(u'Controller not found (may have been deleted): %d', contollerId)
                continue

            controller = indigo.devices[slaveDeviceId]
            self.logger.debug(u'stopping zones on controller: %s', controller.name)

            indigo.sprinkler.stop(controller)

        self._updateActiveDeviceStates(0, 0, 0)

    #---------------------------------------------------------------------------
    def updateStatus(self):
        self.logger.debug(u'update status on master device: %s', self.device.name)

        # look for the active zone on associated controllers
        activeSlaveDevice = self._getActiveSlave()

        activeSlaveId = 0
        activeSlaveZone = 0
        activeMasterZone = 0

        if activeSlaveDevice is not None:
            activeSlaveId = activeSlaveDevice.id
            activeSlaveZone = activeSlaveDevice.activeZone
            activeMasterZone = self._getMasterZoneNumber(activeSlaveDevice, activeSlaveZone)

        self._updateActiveDeviceStates(activeMasterZone, activeSlaveId, activeSlaveZone)

    #---------------------------------------------------------------------------
    def remoteDeviceChanged(self, plugin, device):
        self.logger.debug(u'remote device updated: %s', device.name)

        # XXX ideally, we would only update status for the device that changed
        # instead, update out status to make sure things are kept current

        self.updateStatus()

    #---------------------------------------------------------------------------
    def start(self, plugin):
        self.zoneInfoList = list()

        props = self.device.pluginProps
        controllers = props['controllers']

        if controllers is None or len(controllers) is 0:
            self.logger.warn(u'Nothing to do for device: %s', self.device.name)
            return

        # build the info list from all selected controllers
        for slaveDeviceId in controllers:
            slaveDeviceId = int(slaveDeviceId)

            plugin.watchDeviceForChanges(slaveDeviceId, self.remoteDeviceChanged)

            # sometimes, devices get removed...
            if slaveDeviceId not in indigo.devices:
                self.logger.warn(u'Invalid controller: %s', slaveDeviceId)
                continue

            controller = indigo.devices[slaveDeviceId]

            if controller.enabled is False or controller.configured is False:
                self.logger.warn(u'Controller is not enabled: %s', controller.name)
                continue

            self.logger.debug(u'mapping slave controller: %s', controller.name)
            self._addSlaveController(controller)

        # update device properties based on info list
        numZones = len(self.zoneInfoList)
        zoneNames = [ info['zoneName'] for info in self.zoneInfoList ]
        durations = [ str(info['maxDuration']) for info in self.zoneInfoList ]

        # update inherited props for sprinkler devices
        props['NumZones'] = numZones
        props['ZoneNames'] = ', '.join(zoneNames)
        props['MaxZoneDurations'] = ', '.join(durations)

        self.logger.debug(u'adding %d zones to %s', numZones, self.device.name)
        self.device.replacePluginPropsOnServer(props)

    #---------------------------------------------------------------------------
    def stop(self):
        self.allZonesOff()
        self.zoneInfoList = None

    #---------------------------------------------------------------------------
    def _addSlaveController(self, slaveDevice):
        if self.device.id == slaveDevice.id:
            self.logger.warn(u'Circular device reference: %d', self.device.id)
            return

        # TODO remove current info entries for slaveDevice.id

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

            self.logger.debug(u'adding zone info to list: %s', zoneInfo)
            self.zoneInfoList.append(zoneInfo)

    #---------------------------------------------------------------------------
    def _getActiveSlave(self):
        if self.zoneInfoList is None: return None

        # use set comprehension to avoid duplicate controller ID's
        slaves = { info['controllerId'] for info in self.zoneInfoList }

        activeSlaveDevice = None

        for slaveDeviceId in slaves:

            if slaveDeviceId not in indigo.devices:
                self.logger.warn(u'Controller not found (may have been deleted): %d', contollerId)

            else:
                # get the active zone on the slave controller
                slaveDevice = indigo.devices[slaveDeviceId]
                slaveZoneId = slaveDevice.activeZone

                self.logger.debug(u'active zone on slave: %s -- %s', slaveDevice.name, slaveZoneId)

                # TODO we should check if there are multiple active zones across controllers
                if slaveZoneId is not None and slaveZoneId is not 0:
                    activeSlaveDevice = slaveDevice

        return activeSlaveDevice

    #---------------------------------------------------------------------------
    # TODO find a better way to handle this lookup...
    def _getMasterZoneNumber(self, slaveDevice, slaveZoneNumber=None):
        if slaveZoneNumber is None:
            slaveZoneNumber = slaveDevice.activeZone

        if slaveZoneNumber is 0 or slaveZoneNumber is None:
            return 0

        # find the slave zone ID in the master map
        for masterZoneIndex in range(len(self.zoneInfoList)):
            zoneInfo = self.zoneInfoList[masterZoneIndex]

            if zoneInfo['controllerId'] == slaveDevice.id:
                if zoneInfo['zoneId'] == slaveZoneNumber:
                    return masterZoneIndex + 1

        return None

    #---------------------------------------------------------------------------
    def _prepForNextZone(self, nextControllerId, nextZoneId):
        activeSlaveDevice = self._getActiveSlave()

        # if there is no active program, we are good to go
        if activeSlaveDevice is None:
            return

        activeSlaveId = activeSlaveDevice.id
        self.logger.debug(u'active slave: %d', activeSlaveId)

        # if something is running, but it isn't on the same controller...
        if activeSlaveId != nextControllerId:
            indigo.sprinkler.stop(activeSlaveId)

    #---------------------------------------------------------------------------
    def _updateActiveDeviceStates(self, masterZone, slaveDeviceId=None, slaveZone=None):
        self.logger.debug(u'setting active zone status: %s [%d] => %s:%s',
                          self.device.name, masterZone, slaveDeviceId, slaveZone)

        self.device.updateStateOnServer('activeZone', masterZone)

        if slaveDeviceId is not None:
            self.device.updateStateOnServer('activeSlaveId', slaveDeviceId)

        if slaveZone is not None:
            self.device.updateStateOnServer('activeSlaveZone', slaveZone)

################################################################################
class TestController(ControllerBase):

    #---------------------------------------------------------------------------
    def __init__(self, device):
        ControllerBase.__init__(self, device)

        self.logger = logging.getLogger('Plugin.sprinklers.TestController')

    #---------------------------------------------------------------------------
    def turnZoneOn(self, zone):
        self.logger.info(u'Zone On: %s -- %d', self.device.name, zone)
        self.device.updateStateOnServer('activeZone', zone)

    #---------------------------------------------------------------------------
    def allZonesOff(self):
        self.logger.info(u'All Zones Off: %s', self.device.name)
        self.device.updateStateOnServer('activeZone', 0)

    #---------------------------------------------------------------------------
    def start(self, plugin):
        props = self.device.pluginProps

        durations = props['MaxZoneDurations']
        numZones = len(durations.split(','))
        zoneNames = [ 'Zone {}'.format(idx+1) for idx in range(numZones) ]

        props['NumZones'] = numZones
        props['ZoneNames'] = ', '.join(zoneNames)

        self.device.replacePluginPropsOnServer(props)

