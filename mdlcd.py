#!/usr/bin/env python3
# 
# Copyright (c) 2021, Ben Roberts <ben@benroberts.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import mdstat
from pylcddc import client, widgets, screen
import pylcddc.exceptions as lcdexcept
import argparse
import os
import time
import sys

def scan_mdstat(md, arrays):
    # This routine extracts and interprets the important information out of
    # the dictionary structure that py-mdstat created.
    status = {}
    progress = {}
    #faults = {}
    syncs = {}
    if len(arrays) == 0:
        devices = md['devices']
    else:
        devices = {}
        for a in arrays:
            if a in md['devices']:
                devices[a] = md['devices'][a]
            else:
                status[a] = "missing"

    for d,attrs in devices.items():
        if not attrs['active']:
            status[d] = "inactive"
            continue
        if attrs['resync'] is not None:
            if attrs['resync']['operation'] == "check":
                status[d] = "checking"
            elif attrs['resync']['operation'] == "recovery":
                status[d] = "recovery"
            # TODO catch-all in case there's some other kind of operation
            progress[d] = attrs['resync']['resynced'] / attrs['resync']['total']
        elif attrs['status']['raid_disks'] > attrs['status']['non_degraded_disks']:
            status[d] = "degraded"
            #faults[d] = []
            # Find the faulty disk(s)
            #for disk, disk_attrs in attrs['disks'].items():
            #    if disk_attrs['faulty']:
            #        faults[d].append(disk)
        else:
            status[d] = "ok"

        # Assemble the [UUU_]-style sync status
        syncs[d] = ''.join(["U" if i else "_" for i in attrs['status']['synced']])
    return status, progress, syncs

class ScreenManager:
    def __init__(self, client):
        self._client = client
        self._width, self._height = (client.server_information_response.lcd_width,
                                   client.server_information_response.lcd_height)
        self._cellwid = client.server_information_response.character_width

        self._screens = []
        self._n_per_screen = (self._height - 1 if self._height > 2 else self._height)
        self._titles = (self._height > 2)

    # The array status messages are customized based on LCD width. In some
    # cases sync status can overlap with the message, but they are still
    # distinguishable
    ARRAY_STATUS_MSGS_FULL = {
        "ok": "Clean",
        "missing": "Missing",
        "inactive": "Inactive",
        "degraded": "Degraded",
        "recovery": "Recovering",
        "checking": "Checking"
    }

    ARRAY_STATUS_MSGS_SMALL = {
        "recovery": "Rec",
        "checking": "Chk"
    }

    ARRAY_STATUS_MSGS_TINY = {
        "recovery": "R",
        "checking": "C"
    }

    def status_msg(self, stat):
        if stat != "recovery" and stat != "checking":
            return self.ARRAY_STATUS_MSGS_FULL[stat]
        if self._width < 20:
            return self.ARRAY_STATUS_MSGS_TINY[stat]

        return self.ARRAY_STATUS_MSGS_SMALL[stat]

    def update_screens(self, status, progress, syncs):
        # This method splits up all the status info onto as many screens
        # as needed, then wipes the old ones before sending the new ones to
        # LCDproc. Reusing screens might be more elegant, but it would get
        # quite complex to handle arrays that may appear or disappear between
        # pollings of /proc/mdstat, as well as all the conditional logic
        # involved in which widgets are used for a given array.
        new_screens = []
        curr_dev_count = 0
        curr_widgets = []
        screen_attrs = {}
        devcol = max([len(d) for d in status.items()]) + 1
        titles = (self._titles or len(status) < self._height)
        if titles:
            curr_widgets.append(widgets.Title('status_title_{0}'.format(len(new_screens)), 'mdstat'))

        # The main loop
        for d, stat in status.items():
            # Keep track of which row we're on for the given screen based on
            # how many arrays (or titles) have been placed so far
            y = curr_dev_count + 1 + (1 if titles else 0)

            # Add the array status
            status_text = ("{0:%ds} {1}" % devcol).format(d, self.status_msg(stat))
            text_widget = widgets.String('status_{0}'.format(d), 1, y, status_text)
            curr_widgets.append(text_widget)

            # Add a progress bar if there's an active operation
            if d in progress:
                x = 2 + len(status_text)
                bar_brackets_widgetL = widgets.String('progressbktl_{0}'.format(d), x, y, "[")
                bar_brackets_widgetR = widgets.String('progressbktr_{0}'.format(d), self._width, y, "]")
                bar_width = progress[d] * self._cellwid * (self._width - x - 1)
                bar_widget = widgets.Bar(widgets.WidgetType.HORIZONTAL_BAR,
                        'progress_{0}'.format(d), x + 1, y, bar_width)
                curr_widgets.append(bar_brackets_widgetL)
                curr_widgets.append(bar_brackets_widgetR)
                curr_widgets.append(bar_widget)
            elif d in syncs:
                # Show the traditional [UUU_] sync status like /proc/mdstat
                x = self._width - 1 - len(syncs[d])
                sync_widget = widgets.String('sync_{0}'.format(d), x, y, "[" + syncs[d] + "]")
                curr_widgets.append(sync_widget)
            if stat == "degraded":
                # Flash the backlight if there is at least one degraded array
                screen_attrs["backlight"] = screen.ScreenAttributeValues.Backlight.BLINK

            curr_dev_count += 1

            # If we've filled the available space, add the widgets to a screen
            if curr_dev_count == self._n_per_screen:
                s = screen.Screen('status_{0}'.format(len(new_screens)), curr_widgets, **screen_attrs)
                new_screens.append(s)
                curr_widgets = []
                screen_attrs = {}
                if titles:
                    curr_widgets.append(widgets.Title('status_title_{0}'.format(len(new_screens)), 'mdstat'))
                curr_dev_count = 0
        # Make the last screen if there are widgets to go on it
        if len(curr_widgets) > (1 if titles else 0):
            s = screen.Screen('status_{0}'.format(len(new_screens)), curr_widgets, **screen_attrs)
            new_screens.append(s)

        [self._client.delete_screen(s) for s in self._screens]
        [self._client.add_screen(s) for s in new_screens]
        self._screens = new_screens

def main():
    parser = argparse.ArgumentParser(prog='mdlcd.py', description='LCDproc client for monitoring /proc/mdstat information on RAID arrays')
    parser.add_argument("--host", dest="lcdd_host", default="localhost",
            help="LCDd host")
    parser.add_argument("-p", "--port", dest="lcdd_port", type=int,
            default=13666, help="LCDDd port")
    parser.add_argument("-n", "--poll", dest="pollfreq", type=int,
            default=30, help="Polling interval for mdstat")
    parser.add_argument("-a", "--array", dest="mdarrays", action="append",
            help="Monitor the given device (defaults to all devices)")
    parser.add_argument("--mdstat-file", dest="statfile", help="/proc/mdstat file to monitor (for testing or remote monitoring)")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1")

    args = parser.parse_args()

    try:
        c = client.Client(args.lcdd_host, args.lcdd_port)
        mgr = ScreenManager(c)

        while True:
            arrays = []
            if args.mdarrays is not None:
                for a in args.mdarrays:
                    if os.path.exists(a):
                        # This will dereference any symlinks
                        a = os.path.basename(os.path.realpath(a))
                    else:
                        a = os.path.basename(a)
                    arrays.append(a)

            md = mdstat.parse() if args.statfile is None else mdstat.parse(args.statfile)
            status, progress, syncs = scan_mdstat(md, arrays)

            mgr.update_screens(status, progress, syncs)
            time.sleep(args.pollfreq)
    except lcdexcept.PylcddcError as e:
        print('LCD error', e, file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        if c is not None:
            c.close()

if __name__ == "__main__":
    main()
