# -*- coding: utf-8 -*-
# app2.py
# Copyright (C) 2016-2017 LEAP Encryption Acess Project
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

"""
This is an alternative entrypoint for Bitmask, based on pywebview, to be used
in osx and windows.

For the moment, it requires also qt5 for the systray, but we should move to a
native solution on each platform.
"""

import getpass
import os
import platform
import signal
import sys
import time
import webbrowser

from functools import partial
from multiprocessing import Process

import webview
import psutil

from PyQt5.QtWidgets import QApplication

from leap.bitmask.core.launcher import run_bitmaskd, pid
from leap.common.config import get_path_prefix

from leap.bitmask.gui.systray import WithTrayIcon


DEBUG = os.environ.get("DEBUG", False)

BITMASK_URI = 'http://localhost:7070/'
PIXELATED_URI = 'http://localhost:9090/'

PROCNAME = 'bitmask-app'

qApp = None
bitmaskd = None
browser = None


class Systray(WithTrayIcon):

    def closeFromSystray(self):
        print "SYSTRAY CLOSE"
        global browser
        print "browser is", browser
        self.user_closed = True
        if browser:
            print 'closing browser window'
            browser.shutdown()
            self.close()
        self.close()

    def closeEvent(self, event):
        print "CLOSE EVENT"
        global browser
        print "browser is", browser
        if self.user_closed:
            print "bye!"
            sys.exit()
        else:
            event.ignore()


def launch_systray():
    global qApp
    qApp = QApplication([])
    qApp.setQuitOnLastWindowClosed(True)

    systray = Systray()
    systray.setupSysTray()


class BrowserWindow(object):
    """
    A browser window using pywebview.

    This BrowserWindow assumes that the backend is already running, since it is
    going to look for the authtoken in the configuration folder.
    """

    def __init__(self, *args, **kw):
        url = kw.pop('url', None)
        first = False
        if not url:
            url = "http://localhost:7070"
            path = os.path.join(get_path_prefix(), 'leap', 'authtoken')
            waiting = 20
            while not os.path.isfile(path):
                if waiting == 0:
                    # If we arrive here, something really messed up happened,
                    # because touching the token file is one of the first
                    # things the backend does, and this BrowserWindow
                    # should be called *right after* launching the backend.
                    raise NoAuthToken(
                        'No authentication token found!')
                time.sleep(0.1)
                waiting -= 1
            token = open(path).read().strip()
            url += '#' + token
            first = True
        self.url = url
        self.closing = False

        webview.create_window('Bitmask', self.url)

    def loadPage(self, web_page):
        self.load(url)

    def shutdown(self, *args):
        print "SHUTDOWN from browser window..."
        if self.closing:
            return

        # TODO -- close only if closed from systray!!
        self.closing = True
        global bitmaskd
        bitmaskd.join()
        if os.path.isfile(pid):
            with open(pid) as f:
                pidno = int(f.read())
            print('[bitmask] terminating bitmaskd...')
            os.kill(pidno, signal.SIGTERM)
        print('[bitmask] shutting down gui...')

    def cleanup(self):
        # TODO get path-----------------------------------
        os.remove('/Users/' + getpass.getuser() +
                  '/Library/Preferences/leap/bitmasd.pid')
        # ------------------------------------------------


def launch_gui():
    global bitmaskd
    global browser

    bitmaskd = Process(target=run_bitmaskd)
    bitmaskd.start()

    try:
        launch_systray()
        browser = BrowserWindow(None)
        sys.exit(qApp.exec_())
    except NoAuthToken as e:
        print('ERROR: ' + e.message)
        sys.exit(1)


def start_app():
    from leap.bitmask.util import STANDALONE

    mypid = os.getpid()

    # Kill a previously-running process
    for proc in psutil.process_iter():
        if proc.name() == PROCNAME and proc.pid != mypid:
            proc.kill()

    # Allow the frozen binary in the bundle double as the cli entrypoint
    # Why have only a user interface when you can have two?

    if STANDALONE and len(sys.argv) > 1:
        if sys.argv[1] == 'bitmask_helpers':
            from leap.bitmask.vpn.helpers import main
            return main()

        from leap.bitmask.cli import bitmask_cli
        return bitmask_cli.main()

    prev_auth = os.path.join(get_path_prefix(), 'leap', 'authtoken')
    try:
        os.remove(prev_auth)
    except OSError:
        pass

    launch_gui()


class NoAuthToken(Exception):
    pass


if __name__ == "__main__":
    start_app()
