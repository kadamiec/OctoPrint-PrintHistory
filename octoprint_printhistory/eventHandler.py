# coding=utf-8

__author__ = "Jarek Szczepanski <imrahil@imrahil.com>"
__license__ = "GNU Affero General Public License http://www.gnu.org/licenses/agpl.html"
__copyright__ = "Copyright (C) 2014 Jarek Szczepanski - Released under terms of the AGPLv3 License"

def eventHandler(self, event, payload):
    from octoprint.events import Events
    import json
    import time
    from operator import itemgetter
    from .parser import UniversalParser

    import sqlite3

    supported_event = None

    # support for print done & cancelled events
    if event in [Events.PRINT_DONE, Events.PRINT_FAILED, Events.METADATA_STATISTICS_UPDATED]:
        supported_event = event

    # unsupported event
    if supported_event is None:
        return

    self._logger.info("EVENT TRIGGER: %s" % event)
    if supported_event is not Events.METADATA_STATISTICS_UPDATED:

        fileData = dict()
        retries = 0
        while not 'analysis' in fileData.keys() and retries < 120:
                retries += 1
                try:
                        fileData = self._file_manager.get_metadata(payload["origin"], payload["file"])
                except:
                        fileData = dict()
                time.sleep(1)

        fileName = payload["name"]

        if fileData is not None:
            timestamp = 0
            success = None
            estimatedPrintTime = 0

            gcode_parser = UniversalParser(payload["file"], logger=self._logger)
            parameters = gcode_parser.parse()
            currentFile = {
                "fileName": fileName,
                "note": "",
                "parameters": json.dumps(parameters),
                "user": "",
                "filamentVolume": 0,
                "filamentLength": 0
            }

            if payload["owner"] is not None:
                currentFile["user"] = payload["owner"]

            # analysis - looking for info about filament usage

            #TEMP: log the data
            self._logger.info(fileData)
            
            if "analysis" in fileData:
                if "filament" in fileData["analysis"]:

                    # this never gets to database
                    estimatedPrintTime = fileData["analysis"]["estimatedPrintTime"] if "estimatedPrintTime" in fileData["analysis"] else 0

                    # for Python3 .iteritems() > .items()
                    for (i, tool) in fileData["analysis"]["filament"].iteritems():
                        filamentVolume = tool["volume"]
                        filamentLength = tool["length"]

                        currentFile["filamentVolume"] += filamentVolume if filamentVolume is not None else 0
                        currentFile["filamentLength"] += filamentLength if filamentLength is not None else 0

                        if len(fileData["analysis"]["filament"]) > 1:
                            currentFile["note"] = "Multi extrusion"

            # how long print took
            if "time" in payload:
                currentFile["printTime"] = payload["time"]
            else:
                printTime = self._comm.getPrintTime() if self._comm is not None else ""
                currentFile["printTime"] = printTime


            # when print happened and what was the result
            if "history" in fileData:
                history = fileData["history"]

                newlist = sorted(history, key=itemgetter('timestamp'), reverse=True)

                if newlist:
                    last = newlist[0]

                    success = last["success"]

            if not success:
                success = False if event == Events.PRINT_FAILED or event == Events.PRINT_CANCELLED else True

            timestamp = int(time.time())

            currentFile["success"] = success
            currentFile["timestamp"] = timestamp

            self._history_dict = None

            conn = sqlite3.connect(self._history_db_path)
            cur  = conn.cursor()
            cur.execute("INSERT INTO print_history (fileName, note, filamentVolume, filamentLength, printTime, success, timestamp, parameters, user) VALUES (:fileName, :note, :filamentVolume, :filamentLength, :printTime, :success, :timestamp, :parameters, :user)", currentFile)
            conn.commit()
            conn.close()

    else:
        # sometimes Events.PRINT_DONE is fired BEFORE metadata.yaml is updated - we have to wait for Events.METADATA_STATISTICS_UPDATED and update database
        try:
            fileData = self._file_manager.get_metadata(payload["storage"], payload["path"])
        except:
            fileData = None

        if "history" in fileData:
            history = fileData["history"]

            newlist = sorted(history, key=itemgetter('timestamp'), reverse=True)

            if newlist:
                last = newlist[0]

                success = last["success"]
                timestamp = int(last["timestamp"])

                conn = sqlite3.connect(self._history_db_path)
                cur = conn.cursor()
                cur.execute("UPDATE print_history SET success = ? WHERE timestamp = ?", (success, timestamp))
                conn.commit()
                conn.close()

