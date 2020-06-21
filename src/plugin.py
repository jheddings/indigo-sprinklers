#!/usr/bin/env python2.5

import time
import copy

import iplug

# TODO watch for zones to start from the sub controllers and update status accordingly
# TODO should we filter other virtual master devices out of the selection list?

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

        ############################################
        # XXX requires OverrideScheduleActions property...
        elif action.sprinklerAction == indigo.kSprinklerAction.RunNewSchedule or \
             action.sprinklerAction == indigo.kSprinklerAction.RunPreviousSchedule or \
             action.sprinklerAction == indigo.kSprinklerAction.PauseSchedule or \
             action.sprinklerAction == indigo.kSprinklerAction.ResumeSchedule or \
             action.sprinklerAction == indigo.kSprinklerAction.StopSchedule or \
             action.sprinklerAction == indigo.kSprinklerAction.PreviousZone or \
             action.sprinklerAction == indigo.kSprinklerAction.NextZone:
            pass

    #---------------------------------------------------------------------------
    def _turnZoneOn(self, master, masterZoneNumber):
        self.logger.debug('turning on master zone %d -- %s', masterZoneNumber, master.name)

        # zone numbers are 1-based, but our map starts at 0
        zoneList = self.MasterMap[master.id]
        zoneInfo = zoneList[masterZoneNumber-1]
        zoneName = zoneInfo['zoneName']
        zoneId = zoneInfo['zoneId']
        controllerId = zoneInfo['controllerId']

        if controllerId not in indigo.devices:
            self.logger.warn('controller not found: %d', contollerId)

        else:
            controller = indigo.devices[controllerId]

            self.logger.debug('starting zone %s (%d) on controller: %s',
                              zoneName, zoneId, controller.name)

            indigo.sprinkler.setActiveZone(controller, index=zoneId)
            master.updateStateOnServer("activeZone", masterZoneNumber)

    #---------------------------------------------------------------------------
    def _allZonesOff(self, master):
        self.logger.debug('turn off all zones on master: %s', master.name)
        zoneList = self.MasterMap[master.id]

        # use set comprehension to avoid duplicate controller ID's
        controllers = { info['controllerId'] for info in zoneList }

        # stop watering on all zones attched to this master
        for controllerId in controllers:

            # XXX we don't really need the indigo device to send the stop
            # command, but having the name is nice for logging purposes

            if controllerId not in indigo.devices:
                self.logger.warn('controller not found: %d', contollerId)

            else:
                controller = indigo.devices[controllerId]
                self.logger.debug('stopping zones on controller: %s', controller.name)
                indigo.sprinkler.stop(controller)
                master.updateStateOnServer("activeZone", 0)

    #---------------------------------------------------------------------------
    def _startDevice_MasterController(self, device):

        # reset the master map for the controller device
        self.MasterMap[device.id] = list()

        if 'controllers' not in device.pluginProps:
            self.logger.error('invalid master controller: %s', device.name)
            return

        controllers = device.pluginProps['controllers']

        if len(controllers) <= 0:
            self.logger.error('No remote controllers for device: %s', device.name)
            return

        # build the master map from all selected controllers
        for deviceId in controllers.split(', '):
            deviceId = int(deviceId)

            if deviceId not in indigo.devices:
                self.logger.warn('invalid controller: %s', deviceId)
                continue

            controller = indigo.devices[deviceId]

            if controller.enabled is False or controller.configured is False:
                self.logger.warn('controller is not enabled: %s', controller.name)
                continue

            self.logger.debug('mapping controller: %s', controller.name)
            self._rebuildMasterMap(device, controller)

        # update device properties based on master map
        self._rebuildMasterDeviceProps(device)
        self.logger.info('Sprinkler device "%s" ready', device.name)

    #---------------------------------------------------------------------------
    def _rebuildMasterMap(self, master, remote):
        if master.id == remote.id:
            self.logger.warn('Circular device reference: %d', master.id)
            return

        # TODO remove current master map entries for remote.id

        for idx in range(remote.zoneCount):
            zoneName = remote.zoneNames[idx]
            maxDuration = remote.zoneMaxDurations[idx]
            zoneId = idx + 1

            zoneInfo = {
                'controllerId' : remote.id,
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

        props = device.pluginProps
        props["NumZones"] = len(zoneList)
        props["ZoneNames"] = ', '.join(zoneNames)
        props["MaxZoneDurations"] = ', '.join(durations)
        # if activeScheduleName:
        #     props["ScheduledZoneDurations"] = activeScheduleName

        device.replacePluginPropsOnServer(props)

