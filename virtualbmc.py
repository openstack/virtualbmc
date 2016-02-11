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

import argparse
import signal
import sys
import xml.etree.ElementTree as ET

import libvirt
import pyghmi.ipmi.bmc as bmc

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
                 domain_name, libvirt_uri):
        super(VirtualBMC, self).__init__({username: password},
                                         port=port, address=address)
        self.domain_name = domain_name

        # Create the connection
        self.conn = libvirt.open(libvirt_uri)
        if self.conn is None:
            print('Failed to open connection to the hypervisor '
                  'using the libvirt URI: "%s"' % libvirt_uri)
            sys.exit(1)

        try:
            self.domain = self.conn.lookupByName(self.domain_name)
        except libvirt.libvirtError:
            print('Failed to find the domain "%s"' % self.domain_name)
            sys.exit(1)

    def get_boot_device(self):
        parsed = ET.fromstring(self.domain.XMLDesc())
        boot_devs = parsed.findall('.//os/boot')
        boot_dev = boot_devs[0].attrib['dev']
        return GET_BOOT_DEVICES_MAP.get(boot_dev, 0)

    def set_boot_device(self, bootdevice):
        device = SET_BOOT_DEVICES_MAP.get(bootdevice)
        if device is None:
            print('Uknown boot device: %s' % bootdevice)
            return 0xd5

        parsed = ET.fromstring(self.domain.XMLDesc())
        os = parsed.find('os')
        boot_list = os.findall('boot')

        # Clear boot list
        for boot_el in boot_list:
            os.remove(boot_el)

        boot_el = ET.SubElement(os, 'boot')
        boot_el.set('dev', device)

        try:
            self.conn.defineXML(ET.tostring(parsed))
        except libvirt.libvirtError as e:
            print('Failed setting the boot device to "%s" on the '
                  '"%s" domain' % (device, self.domain_name))

    def get_power_state(self):
        try:
            if self.domain.isActive():
                return POWERON
        except libvirt.libvirtError as e:
           print('Error getting the power state of domain "%s". '
                 'Error: %s' % (self.domain_name, e))
           return

        return POWEROFF

    def power_off(self):
        try:
            self.domain.destroy()
        except libvirt.libvirtError as e:
           print('Error powering off the domain "%s". Error: %s' %
                 (self.domain_name, e))
           return

    def power_on(self):
        try:
            self.domain.create()
        except libvirt.libvirtError as e:
           print('Error powering on the domain "%s". Error: %s' %
                 (self.domain_name, e))
           return


def signal_handler(signal, frame):
    print('SIGINT received, stopping the Virtual BMC...')
    sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='Virtual BMC',
        description='Virtual BMC for controlling virtual instances',
    )
    parser.add_argument('--username',
                        dest='username',
                        default='admin',
                        help='The BMC username; defaults to "admin"')
    parser.add_argument('--password',
                        dest='password',
                        default='password',
                        help='The BMC password; defaults to "password"')
    parser.add_argument('--port',
                        dest='port',
                        type=int,
                        default=623,
                        help='Port to listen on; defaults to 623')
    parser.add_argument('--address',
                        dest='address',
                        default='::',
                        help='Address to bind to; defaults to ::')
    parser.add_argument('--domain-name',
                        dest='domain_name',
                        required=True,
                        help='The name of the virtual machine')
    parser.add_argument('--libvirt-uri',
                        dest='libvirt_uri',
                        default="qemu:///system",
                        help='The libvirt URI; defaults to "qemu:///system"')
    args = parser.parse_args()
    vbmc = VirtualBMC(username=args.username,
                      password=args.password,
                      port=args.port,
                      address=args.address,
                      domain_name=args.domain_name,
                      libvirt_uri=args.libvirt_uri)

    # Register the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Start the virtual BMC
    vbmc.listen()
