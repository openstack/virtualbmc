#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import struct
import time
import xml.etree.ElementTree as ET

import libvirt
from pyghmi import exceptions as ipmi_exception
import pyghmi.ipmi.bmc as bmc
from pyghmi.ipmi.private import session as ipmi_session

from virtualbmc import exception
from virtualbmc import log
from virtualbmc import sol
from virtualbmc import utils

LOG = log.get_logger()

# Power states
POWEROFF = 0
POWERON = 1

# From the IPMI - Intelligent Platform Management Interface Specification
# Second Generation v2.0 Document Revision 1.1 October 1, 2013
# https://www.intel.com/content/dam/www/public/us/en/documents/product-briefs/ipmi-second-gen-interface-spec-v2-rev1-1.pdf
#
# Command failed and can be retried
IPMI_COMMAND_NODE_BUSY = 0xC0
# Invalid data field in request
IPMI_INVALID_DATA = 0xcc
# Payload already active/inactive, depending on the requested operation.
IPMI_PAYLOAD_ALREADY_IN_STATE = 0x80
IPMI_PAYLOAD_UNAVAILABLE = 0x81

# Boot device maps
GET_BOOT_DEVICES_MAP = {
    'network': 4,
    'hd': 8,
    'cdrom': 0x14,
}

SET_BOOT_DEVICES_MAP = {
    'network': 'network',
    'hd': 'hd',
    'optical': 'cdrom',
}


class VirtualBMC(bmc.Bmc):

    def __init__(self, username, password, port, address,
                 domain_name, libvirt_uri, libvirt_sasl_username=None,
                 libvirt_sasl_password=None, **kwargs):
        super(VirtualBMC, self).__init__({username: password},
                                         port=port, address=address)
        self.domain_name = domain_name
        self._conn_args = {'uri': libvirt_uri,
                           'sasl_username': libvirt_sasl_username,
                           'sasl_password': libvirt_sasl_password}
        self.sol = None
        self._console = None

    def activate_payload(self, request, session):
        """Attach the default console to SOL payload instance 1."""
        LOG.debug('SOL activation for %(domain)s from %(peer)s '
                  '(active=%(on)s)',
                  {'domain': self.domain_name, 'peer': session.sockaddr,
                   'on': self.sol is not None})
        if not self._valid_sol_request(request):
            return session.send_ipmi_response(code=IPMI_INVALID_DATA)
        self._expire_sol()
        if self.sol is not None:
            return session.send_ipmi_response(
                code=IPMI_PAYLOAD_ALREADY_IN_STATE)

        bridge = sol.LibvirtConsole(self.domain_name, self._conn_args)
        try:
            bridge.open()
        except (libvirt.libvirtError, exception.VirtualBMCError) as exc:
            LOG.warning('Cannot open SOL console for %(domain)s: %(error)s',
                        {'domain': self.domain_name, 'error': exc})
            return session.send_ipmi_response(code=IPMI_PAYLOAD_UNAVAILABLE)

        self._console = bridge
        try:
            # Sizes include the four-byte SOL header. All three fields are
            # little endian, including non-default vbmc UDP ports.
            data = ([0, 0, 0, 0]
                    + list(struct.pack('<HHH', sol.PAYLOAD_SIZE,
                                       sol.PAYLOAD_SIZE, self.port))
                    + [0xff, 0xff])
            self.sol = sol.ServerConsole(session, self._sol_input)
            session.send_ipmi_response(data=data)
            LOG.info('SOL activated for %s', self.domain_name)
        except Exception:
            self._close_sol()
            raise

    @staticmethod
    def _valid_sol_request(request):
        # SOL payload type 1, instance 1; other payloads are not supported.
        data = request.get('data', [])
        return len(data) == 6 and data[0] == 1 and data[1] == 1

    def deactivate_payload(self, request, session):
        if not self._valid_sol_request(request):
            return session.send_ipmi_response(code=IPMI_INVALID_DATA)
        if self.sol is None:
            return session.send_ipmi_response(
                code=IPMI_PAYLOAD_ALREADY_IN_STATE)
        try:
            session.send_ipmi_response()
        finally:
            self._close_sol()

    def _sol_input(self, console, data):
        if self.sol is not console:
            return
        if isinstance(data, dict):
            if console.broken:
                LOG.debug('SOL transport error for %(domain)s: %(error)s',
                          {'domain': self.domain_name, 'error': data})
                self._close_sol()
        else:
            try:
                self._console.write(data)
            except BufferError:
                LOG.warning('SOL input overflow for %s', self.domain_name)
                self._close_sol()

    def _close_sol(self):
        console, self.sol = self.sol, None
        bridge, self._console = self._console, None
        try:
            if console is not None:
                console.close()
        finally:
            if bridge is not None:
                bridge.close()
                LOG.info('SOL deactivated for %s', self.domain_name)

    def _expire_sol(self):
        if self.sol is None:
            return
        idle = time.monotonic() - self.sol.last_activity
        if (self.sol.broken or not self.sol.activated
                or idle > sol.IDLE_TIMEOUT):
            self._close_sol()

    def _poll_sol(self):
        self._expire_sol()
        console = self.sol
        if console is None:
            return
        data = self._console.poll()
        if data:
            try:
                # pyghmi services IPMI requests while waiting for the ACK.
                console.send_data(data)
            except (ipmi_exception.IpmiException, OSError) as exc:
                LOG.warning('SOL output failed for %(domain)s: %(error)s',
                            {'domain': self.domain_name, 'error': exc})
                # A new client may have activated SOL during send_data().
                if self.sol is console:
                    self._close_sol()

    def handle_raw_request(self, request, session):
        if self.sol is not None and self.sol.ipmi_session is session:
            # ipmitool uses Get Device ID as its default SOL keepalive.
            self.sol.last_activity = time.monotonic()
        super(VirtualBMC, self).handle_raw_request(request, session)

    def listen(self, timeout=30):
        # Initialized in the per-domain child, after multiprocessing forks.
        libvirt.virEventRegisterDefaultImpl()
        timer = libvirt.virEventAddTimeout(
            int(sol.POLL_INTERVAL * 1000), lambda timer, opaque: None, None)
        try:
            while True:
                if self.sol is None:
                    ipmi_session.Session.wait_for_rsp(timeout)
                else:
                    ipmi_session.Session.wait_for_rsp(0)
                    libvirt.virEventRunDefaultImpl()
                self._poll_sol()
        finally:
            self._close_sol()
            libvirt.virEventRemoveTimeout(timer)

    # Copied from nova/virt/libvirt/guest.py
    def get_xml_desc(self, domain, dump_sensitive=False):
        """Returns xml description of guest.

        :param domain: The libvirt domain to call
        :param dump_sensitive: Dump security sensitive information
        :returns string: XML description of the guest
        """
        flags = dump_sensitive and libvirt.VIR_DOMAIN_XML_SECURE or 0
        return domain.XMLDesc(flags=flags)

    def get_boot_device(self):
        LOG.debug('Get boot device called for %(domain)s',
                  {'domain': self.domain_name})
        with utils.libvirt_open(readonly=True, **self._conn_args) as conn:
            domain = utils.get_libvirt_domain(conn, self.domain_name)
            boot_element = ET.fromstring(domain.XMLDesc()).find('.//os/boot')
            boot_dev = None
            if boot_element is not None:
                boot_dev = boot_element.attrib.get('dev')
            return GET_BOOT_DEVICES_MAP.get(boot_dev, 0)

    def _remove_boot_elements(self, parent_element):
        for boot_element in parent_element.findall('boot'):
            parent_element.remove(boot_element)

    def set_boot_device(self, bootdevice):
        LOG.debug('Set boot device called for %(domain)s with boot '
                  'device "%(bootdev)s"', {'domain': self.domain_name,
                                           'bootdev': bootdevice})
        device = SET_BOOT_DEVICES_MAP.get(bootdevice)
        if device is None:
            # Invalid data field in request
            return IPMI_INVALID_DATA

        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                tree = ET.fromstring(
                    self.get_xml_desc(domain, dump_sensitive=True))

                # Remove all "boot" element under "devices"
                # They are mutually exclusive with "os/boot"
                for device_element in tree.findall('devices/*'):
                    self._remove_boot_elements(device_element)

                for os_element in tree.findall('os'):
                    # Remove all "boot" elements under "os"
                    self._remove_boot_elements(os_element)

                    # Add a new boot element with the request boot device
                    boot_element = ET.SubElement(os_element, 'boot')
                    boot_element.set('dev', device)

                conn.defineXML(ET.tostring(tree, encoding="unicode"))
        except Exception:
            LOG.error('Failed setting the boot device %(bootdev)s for '
                      'domain %(domain)s', {'bootdev': device,
                                            'domain': self.domain_name})
            # Command failed, but let client to retry
            return IPMI_COMMAND_NODE_BUSY

    def get_power_state(self):
        LOG.debug('Get power state called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(readonly=True, **self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    return POWERON
        except Exception as e:
            msg = ('Error getting the power state of domain %(domain)s. '
                   'Error: %(error)s' % {'domain': self.domain_name,
                                         'error': e})
            LOG.error(msg)
            raise exception.VirtualBMCError(message=msg)

        return POWEROFF

    def pulse_diag(self):
        LOG.debug('Power diag called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.injectNMI()
        except Exception as e:
            LOG.error('Error powering diag the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command failed, but let client to retry
            return IPMI_COMMAND_NODE_BUSY

    def power_off(self):
        LOG.debug('Power off called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.destroy()
        except Exception as e:
            LOG.error('Error powering off the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command failed, but let client to retry
            return IPMI_COMMAND_NODE_BUSY

    def power_on(self):
        LOG.debug('Power on called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if not domain.isActive():
                    domain.create()
        except Exception as e:
            LOG.error('Error powering on the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command failed, but let client to retry
            return IPMI_COMMAND_NODE_BUSY

    def power_shutdown(self):
        LOG.debug('Soft power off called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.shutdown()
        except Exception as e:
            LOG.error('Error soft powering off the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command failed, but let client to retry
            return IPMI_COMMAND_NODE_BUSY

    def power_reset(self):
        LOG.debug('Power reset called for domain %(domain)s',
                  {'domain': self.domain_name})
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.reset()
        except Exception as e:
            LOG.error('Error resetting the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command not supported in present state
            return IPMI_COMMAND_NODE_BUSY
