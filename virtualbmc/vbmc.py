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

import xml.etree.ElementTree as ET

import libvirt
import pyghmi.ipmi.bmc as bmc

from virtualbmc import exception
from virtualbmc import log
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
                tree = ET.fromstring(domain.XMLDesc())

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
        except libvirt.libvirtError:
            LOG.error('Failed setting the boot device  %(bootdev)s for '
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
        except libvirt.libvirtError as e:
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
        except libvirt.libvirtError as e:
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
        except libvirt.libvirtError as e:
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
        except libvirt.libvirtError as e:
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
        except libvirt.libvirtError as e:
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
        except libvirt.libvirtError as e:
            LOG.error('Error reseting the domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command not supported in present state
            return IPMI_COMMAND_NODE_BUSY
