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

import os
import xml.etree.ElementTree as ET

import libvirt
import pyghmi.ipmi.bmc as bmc

import exception
import log

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


class libvirt_open(object):

    def __init__(self, uri, readonly=False):
        self.uri = uri
        self.readonly = readonly

    def __enter__(self):
        try:
            if self.readonly:
                self.conn = libvirt.openReadOnly(self.uri)
            else:
                self.conn = libvirt.open(self.uri)

            return self.conn

        except libvirt.libvirtError as e:
            raise exception.LibvirtConnectionOpenError(uri=self.uri, error=e)

    def __exit__(self, type, value, traceback):
        self.conn.close()


def get_libvirt_domain(conn, domain):
    try:
        return conn.lookupByName(domain)
    except libvirt.libvirtError:
        raise exception.DomainNotFound(domain=domain)


def check_libvirt_connection_and_domain(uri, domain):
    with libvirt_open(uri, readonly=True) as conn:
        get_libvirt_domain(conn, domain)


class VirtualBMC(bmc.Bmc):

    def __init__(self, username, password, port, address,
                 domain_name, libvirt_uri):
        super(VirtualBMC, self).__init__({username: password},
                                         port=port, address=address)
        self.libvirt_uri = libvirt_uri
        self.domain_name = domain_name

    def get_boot_device(self):
        LOG.debug('Get boot device called for %s', self.domain_name)
        with libvirt_open(self.libvirt_uri, readonly=True) as conn:
            domain = get_libvirt_domain(conn, self.domain_name)
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
            return 0xd5

        with libvirt_open(self.libvirt_uri) as conn:
            domain = get_libvirt_domain(conn, self.domain_name)
            tree = ET.fromstring(domain.XMLDesc())

            for os_element in tree.findall('os'):
                # Remove all "boot" elements
                for boot_element in os_element.findall('boot'):
                    os_element.remove(boot_element)

                # Add a new boot element with the request boot device
                boot_element = ET.SubElement(os_element, 'boot')
                boot_element.set('dev', device)

            try:
                conn.defineXML(ET.tostring(tree))
            except libvirt.libvirtError as e:
                LOG.error('Failed setting the boot device  %(bootdev)s for '
                          'domain %(domain)s', {'bootdev': device,
                                                'domain': self.domain_name})

    def get_power_state(self):
        LOG.debug('Get power state called for domain %s', self.domain_name)
        try:
            with libvirt_open(self.libvirt_uri, readonly=True) as conn:
                domain = get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    return POWERON
        except libvirt.libvirtError as e:
            LOG.error('Error getting the power state of domain %(domain)s. '
                      'Error: %(error)s', {'domain': self.domain_name,
                                           'error': e})
            return

        return POWEROFF

    def power_off(self):
        LOG.debug('Power off called for domain %s', self.domain_name)
        try:
            with libvirt_open(self.libvirt_uri) as conn:
                domain = get_libvirt_domain(conn, self.domain_name)
                if domain.isActive():
                    domain.destroy()
        except libvirt.libvirtError as e:
            LOG.error('Error powering off the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            return

    def power_on(self):
        LOG.debug('Power on called for domain %s', self.domain_name)
        try:
            with libvirt_open(self.libvirt_uri) as conn:
                domain = get_libvirt_domain(conn, self.domain_name)
                if not domain.isActive():
                    domain.create()
        except libvirt.libvirtError as e:
            LOG.error('Error powering on the domain %(domain)s. '
                      'Error: %(error)s' % {'domain': self.domain_name,
                                            'error': e})
            return
