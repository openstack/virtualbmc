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

from virtualbmc import log
from virtualbmc import utils

LOG = log.get_logger()

# Power states
POWEROFF = 0
POWERON = 1

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
                 libvirt_sasl_password=None):
        super(VirtualBMC, self).__init__({username: password},
                                         port=port, address=address)
        self.domain_name = domain_name
        self._conn_args = {'uri': libvirt_uri,
                           'sasl_username': libvirt_sasl_username,
                           'sasl_password': libvirt_sasl_password}

    def get_boot_device(self):
        LOG.debug('Get boot device called for %s', self.domain_name)
        with utils.libvirt_open(readonly=True, **self._conn_args) as conn:
            domain = utils.get_libvirt_domain(conn, self.domain_name)
            boot_element = ET.fromstring(domain.XMLDesc()).find('.//os/boot')
            boot_dev = None
            if boot_element is not None:
                boot_dev = boot_element.attrib.get('dev')
            return GET_BOOT_DEVICES_MAP.get(boot_dev, 0)

    def set_boot_device(self, bootdevice):
        LOG.debug('Set boot device called for %(domain)s with boot '
                  'device "%(bootdev)s"', {'domain': self.domain_name,
                                           'bootdev': bootdevice})
        device = SET_BOOT_DEVICES_MAP.get(bootdevice)
        if device is None:
            # Invalid data field in request
            return 0xcc

        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                tree = ET.fromstring(domain.XMLDesc())

                for os_element in tree.findall('os'):
                    # Remove all "boot" elements
                    for boot_element in os_element.findall('boot'):
                        os_element.remove(boot_element)

                    # Add a new boot element with the request boot device
                    boot_element = ET.SubElement(os_element, 'boot')
                    boot_element.set('dev', device)

                conn.defineXML(ET.tostring(tree))
        except libvirt.libvirtError:
            LOG.error('Failed setting the boot device  %(bootdev)s for '
                      'domain %(domain)s', {'bootdev': device,
                                            'domain': self.domain_name})
            # Command not supported in present state
            return 0xd5

    def get_power_state(self):
        LOG.debug('Get power state called for domain %s', self.domain_name)
        try:
            with utils.libvirt_open(readonly=True, **self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    return POWERON
        except libvirt.libvirtError as e:
            LOG.error('Error getting the power state of domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            # Command not supported in present state
            return 0xd5

        return POWEROFF

    def pulse_diag(self):
        LOG.debug('Power diag called for domain %s', self.domain_name)
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.injectNMI()
        except libvirt.libvirtError as e:
            LOG.error('Error powering diag the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            # Command not supported in present state
            return 0xd5

    def power_off(self):
        LOG.debug('Power off called for domain %s', self.domain_name)
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.destroy()
        except libvirt.libvirtError as e:
            LOG.error('Error powering off the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            # Command not supported in present state
            return 0xd5

    def power_on(self):
        LOG.debug('Power on called for domain %s', self.domain_name)
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if not domain.isActive():
                    domain.create()
        except libvirt.libvirtError as e:
            LOG.error('Error powering on the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            # Command not supported in present state
            return 0xd5

    def power_shutdown(self):
        LOG.debug('Soft power off called for domain %s', self.domain_name)
        try:
            with utils.libvirt_open(**self._conn_args) as conn:
                domain = utils.get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.shutdown()
        except libvirt.libvirtError as e:
            LOG.error('Error soft powering off the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            # Command not supported in present state
            return 0xd5
