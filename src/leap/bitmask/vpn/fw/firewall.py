# -*- coding: utf-8 -*-
# manager.py
# Copyright (C) 2015 LEAP
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
# alng with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Firewall Manager
"""

import commands
import os
import subprocess

from twisted.logger import Logger

from leap.bitmask.util import STANDALONE
from leap.bitmask.system import IS_MAC, IS_LINUX, IS_SNAP
from leap.bitmask.vpn.constants import BITMASK_ROOT_SYSTEM
from leap.bitmask.vpn.constants import BITMASK_ROOT_LOCAL
from leap.bitmask.vpn.constants import BITMASK_ROOT_SNAP
from leap.common.events import catalog, emit_async

from leap.bitmask.vpn.launchers import darwin

log = Logger()

# A regular user should not run bitmask as root, but we contemplate
# this case for tests inside docker.

NOT_ROOT = os.getuid() != 0


def check_root(cmd):
    if NOT_ROOT:
        cmd = ['pkexec'] + cmd
    return cmd


class FirewallError(Exception):
    pass


class _OSXFirewallManager(object):
    def __init__(self, remotes):
        self._remotes = list(remotes)
        self._helper = darwin.HelperCommand()
        self._started = False

    def start(self, restart=False):
        gateways = [gateway for gateway, port in self._remotes]
        cmd = 'firewall_start %s' % (' '.join(gateways),)
        self._helper.send(cmd)
        self._started = True
        # TODO parse OK from result
        return True

    def stop(self):
        cmd = 'firewall_stop'
        self._helper.send(cmd)
        self._started = False
        return True

    def is_up(self):
        # TODO implement!!!
        return self._started

    @property
    def status(self):
        # TODO implement!!! -- factor out, too
        status = 'on' if self._started else 'off'
        return {'status': status, 'error': None}


class _LinuxFirewallManager(object):

    """
    Firewall manager that blocks/unblocks all the internet traffic with some
    exceptions.
    This allows us to achieve fail close on a vpn connection.
    """

    # TODO factor out choosing a version of bitmask-root.
    # together with linux vpnlauncher.

    if IS_SNAP:
        # snap has its own version under /snap
        BITMASK_ROOT = BITMASK_ROOT_SNAP
    elif STANDALONE and os.path.isfile(BITMASK_ROOT_LOCAL):
        # if this is a bundle, we pick local. bundles ask to install it there.
        BITMASK_ROOT = BITMASK_ROOT_LOCAL
    else:
        if os.path.isfile(BITMASK_ROOT_SYSTEM):
            # we can be running from the debian package,
            # or some other distro. it's the maintainer responsibility to put
            # bitmask-root there.
            BITMASK_ROOT = BITMASK_ROOT_SYSTEM
        else:
            # as a last case, we fall back to installing into the
            # /usr/local/sbin version.
            BITMASK_ROOT = BITMASK_ROOT_LOCAL

    def __init__(self, remotes):
        """
        Initialize the firewall manager with a set of remotes that we won't
        block.

        :param remotes: the gateway(s) that we will allow
        :type remotes: list
        """
        self._remotes = remotes

    def start(self, restart=False):
        """
        Launch the firewall using the privileged wrapper.

        :returns: True if the exitcode of calling the root helper in a
                  subprocess is 0.
        :rtype: bool
        """
        gateways = [gateway for gateway, port in self._remotes]

        # XXX check for wrapper existence, check it's root owned etc.
        # XXX check that the iptables rules are in place.

        cmd = [self.BITMASK_ROOT, "firewall", "start"]
        cmd = check_root(cmd)

        if restart:
            cmd.append("restart")
        result = '<did not run>'
        if not os.path.isfile(self.BITMASK_ROOT):
            raise FirewallError('Could not find bitmask-root!')
        try:
            retcode, result = commands.getstatusoutput(
                ' '.join(cmd + gateways))
        except Exception:
            msg = 'Error launching the firewall'
            log.failure(msg)
            if NOT_ROOT:
                raise FirewallError(msg)
        finally:
            log.debug(result)
        emit_async(catalog.VPN_STATUS_CHANGED, "FW_ON")
        return True

    def stop(self):
        """
        Tear the firewall down using the privileged wrapper.
        """
        cmd = [self.BITMASK_ROOT, "firewall", "stop"]
        cmd = check_root(cmd)
        exitCode = subprocess.call(cmd)
        emit_async(catalog.VPN_STATUS_CHANGED, "FW_OFF")
        if exitCode == 0:
            return True
        else:
            return False

    def is_up(self):
        """
        Return whether the firewall is up or not.

        :rtype: bool
        """
        cmd = [self.BITMASK_ROOT, "firewall", "isup"]
        cmd = check_root(cmd)
        cmd = ' '.join(cmd)
        output = commands.getstatusoutput(cmd)[0]

        return output != 256

    @property
    def status(self):
        status = 'off'
        if self.is_up():
            status = 'on'

        return {'status': status, 'error': None}


if IS_LINUX:
    FirewallManager = _LinuxFirewallManager
elif IS_MAC:
    FirewallManager = _OSXFirewallManager
