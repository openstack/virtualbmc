# Portions of ServerConsole adapted from pyghmi.ipmi.console:
# Copyright 2014 IBM Corporation
# Copyright 2015-2019 Lenovo
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Single-client SOL transport and a nonblocking libvirt console bridge."""

import contextlib
import threading
import time
import xml.etree.ElementTree as ET

import libvirt
from pyghmi import exceptions as ipmi_exception
from pyghmi.ipmi import console

from virtualbmc import exception
from virtualbmc import log
from virtualbmc import utils

LOG = log.get_logger()

# The SOL accepted-character count is only one byte wide.
CHARACTERS_PER_PACKET = 255
PAYLOAD_SIZE = CHARACTERS_PER_PACKET + 4
MAX_PENDING_INPUT = 4096
RECONNECT_INTERVAL = 1
IDLE_TIMEOUT = 60
POLL_INTERVAL = 0.02
SOL_INACTIVE = 0x10


class ServerConsole(console.ServerConsole):
    """Adapt pyghmi's SOL transport to a BMC-owned console.

    ``iohandler(console, data)`` receives bytes or a transport error dict.
    """

    def __init__(self, session, iohandler):
        # Adapted from pyghmi 1.2.0--1.6.19, without wait_for_rsp(0):
        # reentering the IPMI loop here can process a retransmitted activation
        # before we have replied to the first request.
        self.outputlock = threading.RLock()
        self.keepaliveid = None
        self.connected = True
        self.broken = False
        self.out_handler = lambda data: iohandler(self, data)
        self.remseq = 0
        self.myseq = 0
        self.lastsize = 0
        self.retriedpayload = 0
        self.pendingoutput = []
        self.awaitingack = False
        self.activated = True
        self.force_session = False
        self.ipmi_session = session
        self.ipmi_session.sol_handler = self._got_sol_payload
        self.poweredon = True
        self.last_activity = time.monotonic()
        self.maxoutcount = CHARACTERS_PER_PACKET

    def _got_sol_payload(self, payload):
        if (not isinstance(payload, dict)
                and not 4 <= len(payload) <= PAYLOAD_SIZE):
            return
        self.last_activity = time.monotonic()
        super(ServerConsole, self)._got_sol_payload(payload)

    def _print_error(self, error):
        # ServerSession lacks the client keepalive state used by pyghmi's
        # inherited error handler.
        self.broken = True
        self.close(notify=False)
        self.out_handler(error if isinstance(error, dict)
                         else {'error': error})

    def send_payload(self, payload, payload_type=1, retry=True,
                     needskeepalive=False):
        if not self.activated:
            return
        try:
            super(ServerConsole, self).send_payload(
                payload, payload_type=payload_type, retry=retry,
                needskeepalive=needskeepalive)
        except (ipmi_exception.IpmiException, OSError) as exc:
            self._print_error(str(exc))

    def close(self, notify=True):
        """Release the session callback and cancel any outstanding output."""
        session, self.ipmi_session = self.ipmi_session, None
        self.activated = False
        self.connected = False
        self.awaitingack = False
        self.pendingoutput = []
        if session is None or session.sol_handler != self._got_sol_payload:
            return
        session.sol_handler = None
        if notify:
            try:
                session.send_payload(bytearray([0, 0, 0, SOL_INACTIVE]),
                                     payload_type=1, retry=False)
            except (ipmi_exception.IpmiException, OSError) as exc:
                LOG.debug('Could not notify disconnected SOL client: %s', exc)


class LibvirtConsole(object):
    """Nonblocking console stream, serviced in the BMC's event loop."""

    def __init__(self, domain_name, conn_args):
        self.domain_name = domain_name
        self.conn_args = conn_args
        self._resources = contextlib.ExitStack()
        self._conn = None
        self._domain = None
        self._stream = None
        self._pending = b''
        self._retry_at = 0

    def open(self):
        """Connect to libvirt and attach the console if the guest is active."""
        try:
            self._conn = self._resources.enter_context(
                utils.libvirt_open(**self.conn_args))
            self._domain = utils.get_libvirt_domain(
                self._conn, self.domain_name)
            tree = ET.fromstring(self._domain.XMLDesc())
            if (tree.find('./devices/console') is None
                    and tree.find('./devices/serial') is None):
                raise exception.ConsoleNotFound(domain=self.domain_name)
            self._attach()
        except Exception:
            self.close()
            raise

    def _attach(self):
        if self._domain.isActive():
            self._stream = self._conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
            # Do not steal a console from virsh or another SOL instance.
            self._domain.openConsole(None, self._stream,
                                     libvirt.VIR_DOMAIN_CONSOLE_SAFE)

    def write(self, data):
        """Queue input, discarding keystrokes while the stream is absent."""
        if self._stream is None:
            return
        if len(self._pending) + len(data) > MAX_PENDING_INPUT:
            raise BufferError('SOL console input buffer is full')
        self._pending += data

    def poll(self):
        """Flush queued input and return at most one SOL packet of output."""
        if self._stream is None:
            if time.monotonic() < self._retry_at:
                return b''
            try:
                if self._conn is None:
                    self.open()
                else:
                    self._attach()
            except (libvirt.libvirtError, exception.VirtualBMCError) as exc:
                LOG.debug('SOL console reconnect for %(domain)s: %(error)s',
                          {'domain': self.domain_name, 'error': exc})
                self.close()
                return b''
            finally:
                self._retry_at = time.monotonic() + RECONNECT_INTERVAL

        if self._stream is None:
            return b''

        try:
            if self._pending:
                sent = self._stream.send(self._pending)
                if sent > 0:
                    self._pending = self._pending[sent:]
                # -2 means would block; retain the entire remaining input.
            data = self._stream.recv(CHARACTERS_PER_PACKET)
            if data == -2:
                return b''
            if data:
                return data
        except libvirt.libvirtError as exc:
            LOG.debug('SOL console disconnected for %(domain)s: %(error)s',
                      {'domain': self.domain_name, 'error': exc})

        # EOF or error: release the old connection and retry on a later tick.
        self.close()
        self._retry_at = time.monotonic() + RECONNECT_INTERVAL
        return b''

    def close(self):
        """Release the stream and connection, discarding pending input."""
        stream, self._stream = self._stream, None
        self._conn = self._domain = None
        self._pending = b''
        try:
            if stream is not None:
                stream.abort()
        except libvirt.libvirtError:
            pass
        finally:
            try:
                self._resources.close()
            except libvirt.libvirtError:
                pass
