# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
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

import libvirt
import mock

from virtualbmc.tests.unit import base
from virtualbmc.tests.unit import utils as test_utils
from virtualbmc import utils
from virtualbmc import vbmc

DOMAIN_XML_TEMPLATE = """\
<domain type='qemu'>
  <os>
    <type arch='x86_64' machine='pc-1.0'>hvm</type>
    <boot dev='%s'/>
    <bootmenu enable='no'/>
    <bios useserial='yes'/>
  </os>
</domain>
"""


@mock.patch.object(utils, 'libvirt_open')
@mock.patch.object(utils, 'get_libvirt_domain')
class VirtualBMCTestCase(base.TestCase):

    def setUp(self):
        super(VirtualBMCTestCase, self).setUp()
        self.domain = test_utils.get_domain()
        # NOTE(lucasagomes): pyghmi's Bmc does create a socket in the
        # constructor so we need to mock it here
        mock.patch('pyghmi.ipmi.bmc.Bmc.__init__',
                   lambda *args, **kwargs: None).start()
        self.vbmc = vbmc.VirtualBMC(**self.domain)

    def _assert_libvirt_calls(self, mock_libvirt_domain, mock_libvirt_open,
                              readonly=False):
        """Helper method to assert that the LibVirt calls were invoked."""
        mock_libvirt_domain.assert_called_once_with(
            mock.ANY, self.domain['domain_name'])
        params = {'sasl_password': self.domain['libvirt_sasl_password'],
                  'sasl_username': self.domain['libvirt_sasl_username'],
                  'uri': self.domain['libvirt_uri']}
        if readonly:
            params['readonly'] = True
        mock_libvirt_open.assert_called_once_with(**params)

    def test_get_boot_device(self, mock_libvirt_domain, mock_libvirt_open):
        for boot_device in vbmc.GET_BOOT_DEVICES_MAP:
            domain_xml = DOMAIN_XML_TEMPLATE % boot_device
            mock_libvirt_domain.return_value.XMLDesc.return_value = domain_xml
            ret = self.vbmc.get_boot_device()

            self.assertEqual(vbmc.GET_BOOT_DEVICES_MAP[boot_device], ret)
            self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open,
                                       readonly=True)

            # reset mocks for the next iteraction
            mock_libvirt_domain.reset_mock()
            mock_libvirt_open.reset_mock()

    def test_set_boot_device(self, mock_libvirt_domain, mock_libvirt_open):
        for boot_device in vbmc.SET_BOOT_DEVICES_MAP:
            domain_xml = DOMAIN_XML_TEMPLATE % 'foo'
            mock_libvirt_domain.return_value.XMLDesc.return_value = domain_xml
            conn = mock_libvirt_open.return_value.__enter__.return_value
            self.vbmc.set_boot_device(boot_device)

            expected = ('<boot dev="%s" />' %
                        vbmc.SET_BOOT_DEVICES_MAP[boot_device])
            self.assertIn(expected, str(conn.defineXML.call_args))
            self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

            # reset mocks for the next iteraction
            mock_libvirt_domain.reset_mock()
            mock_libvirt_open.reset_mock()

    def test_set_boot_device_error(self, mock_libvirt_domain,
                                   mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.set_boot_device('network')
        self.assertEqual(0xd5, ret)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_set_boot_device_unkown_device_error(self, mock_libvirt_domain,
                                                 mock_libvirt_open):
        ret = self.vbmc.set_boot_device('device-foo-bar')
        self.assertEqual(0xcc, ret)
        self.assertFalse(mock_libvirt_open.called)
        self.assertFalse(mock_libvirt_domain.called)

    def _test_get_power_state(self, mock_libvirt_domain, mock_libvirt_open,
                              power_on=True):
        mock_libvirt_domain.return_value.isActive.return_value = power_on
        ret = self.vbmc.get_power_state()

        expected = vbmc.POWERON if power_on else vbmc.POWEROFF
        self.assertEqual(expected, ret)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open,
                                   readonly=True)

    def test_get_power_state_on(self, mock_libvirt_domain, mock_libvirt_open):
        self._test_get_power_state(mock_libvirt_domain, mock_libvirt_open,
                                   power_on=True)

    def test_get_power_state_off(self, mock_libvirt_domain, mock_libvirt_open):
        self._test_get_power_state(mock_libvirt_domain, mock_libvirt_open,
                                   power_on=False)

    def test_get_power_state_error(self, mock_libvirt_domain,
                                   mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.get_power_state()
        self.assertEqual(0xd5, ret)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open,
                                   readonly=True)

    def test_pulse_diag_is_on(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        self.vbmc.pulse_diag()

        domain.injectNMI.assert_called_once_with()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_pulse_diag_is_off(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        self.vbmc.pulse_diag()

        # power is already off, assert injectNMI() wasn't invoked
        domain.injectNMI.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_pulse_diag_error(self, mock_libvirt_domain, mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.pulse_diag()
        self.assertEqual(0xd5, ret)
        mock_libvirt_domain.return_value.injectNMI.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_off_is_on(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        self.vbmc.power_off()

        domain.destroy.assert_called_once_with()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_off_is_off(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        self.vbmc.power_off()

        # power is already off, assert destroy() wasn't invoked
        domain.destroy.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_off_error(self, mock_libvirt_domain, mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.power_off()
        self.assertEqual(0xd5, ret)
        mock_libvirt_domain.return_value.destroy.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_shutdown_is_on(self, mock_libvirt_domain,
                                  mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        self.vbmc.power_shutdown()

        domain.shutdown.assert_called_once_with()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_shutdown_is_off(self, mock_libvirt_domain,
                                   mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        self.vbmc.power_shutdown()

        # power is already off, assert shutdown() wasn't invoked
        domain.shutdown.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_shutdown_error(self, mock_libvirt_domain,
                                  mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.power_shutdown()
        self.assertEqual(0xd5, ret)
        mock_libvirt_domain.return_value.shutdown.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_on_is_on(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        self.vbmc.power_on()

        # power is already on, assert create() wasn't invoked
        domain.create.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_on_is_off(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        self.vbmc.power_on()

        domain.create.assert_called_once_with()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_on_error(self, mock_libvirt_domain, mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.power_on()
        self.assertEqual(0xd5, ret)
        self.assertFalse(mock_libvirt_domain.return_value.create.called)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)
