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
import threading

from pyghmi.ipmi import bmc
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
  <devices>
    <disk type='block' device='disk'>
      <boot order='2'/>
    </disk>
    <interface type='network'>
      <boot order='1'/>
    </interface>
  </devices>
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
            self.assertEqual(1, str(conn.defineXML.call_args).count('<boot '))
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

    def test_power_reset_is_on(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        self.vbmc.power_reset()

        domain.reset.assert_called_once_with()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_reset_is_off(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        self.vbmc.power_reset()

        # power is already off, assert reset() wasn't invoked
        domain.reset.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_power_reset_error(self, mock_libvirt_domain, mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.power_reset()
        self.assertEqual(0xd5, ret)
        mock_libvirt_domain.return_value.reset.assert_not_called()
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

    def test_is_active_active(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = True
        ret = self.vbmc.is_active()

        # power is already on, assert create() wasn't invoked
        self.assertEqual(ret, True)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_is_active_inactive(self, mock_libvirt_domain, mock_libvirt_open):
        domain = mock_libvirt_domain.return_value
        domain.isActive.return_value = False
        ret = self.vbmc.is_active()

        self.assertEqual(ret, False)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_is_active_error(self, mock_libvirt_domain, mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        ret = self.vbmc.is_active()
        self.assertEqual(ret, None)
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    def test_iohandler(self, mock_libvirt_domain, mock_libvirt_open):
        mock_stream = mock.MagicMock()
        self.vbmc._stream = mock_stream
        self.vbmc.iohandler('foo')
        mock_stream.send.assert_called_with('foo')

    def test_iohandler_empty_stream(self, mock_libvirt_domain,
                                    mock_libvirt_open):
        self.vbmc._stream = None
        self.vbmc.iohandler('foo')

    def test_check_console(self, mock_libvirt_domain, mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_domain = mock.MagicMock()
        self.vbmc._conn = mock_conn
        self.vbmc._domain = mock_domain
        self.vbmc._run_console = True
        self.vbmc._state = [libvirt.VIR_DOMAIN_RUNNING]
        self.vbmc._stream = None
        ret = self.vbmc.check_console()

        mock_conn.newStream.assert_called()
        mock_domain.openConsole.assert_called()
        mock_stream = mock_conn.newStream.return_value
        mock_stream.eventAddCallback.assert_called()
        mock_stream.eventRemoveCallback.assert_not_called()
        self.assertEqual(ret, True)

    def test_check_console_stream(self, mock_libvirt_domain,
                                  mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_domain = mock.MagicMock()
        mock_stream = mock.MagicMock()
        self.vbmc._conn = mock_conn
        self.vbmc._domain = mock_domain
        self.vbmc._run_console = True
        self.vbmc._state = [libvirt.VIR_DOMAIN_RUNNING]
        self.vbmc._stream = mock_stream
        ret = self.vbmc.check_console()

        mock_conn.newStream.assert_not_called()
        mock_domain.openConsole.assert_not_called()
        mock_stream.eventAddCallback.assert_not_called()
        mock_stream.eventRemoveCallback.assert_not_called()
        self.assertEqual(ret, True)

    def test_check_console_shutoff(self, mock_libvirt_domain,
                                   mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_domain = mock.MagicMock()
        self.vbmc._conn = mock_conn
        self.vbmc._domain = mock_domain
        self.vbmc._run_console = True
        self.vbmc._state = [libvirt.VIR_DOMAIN_SHUTOFF]
        self.vbmc._stream = None
        ret = self.vbmc.check_console()

        mock_conn.newStream.assert_not_called()
        mock_domain.openConsole.assert_not_called()
        self.assertEqual(ret, True)

    def test_check_console_shutoff_stream(self, mock_libvirt_domain,
                                          mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_domain = mock.MagicMock()
        mock_stream = mock.MagicMock()
        self.vbmc._conn = mock_conn
        self.vbmc._domain = mock_domain
        self.vbmc._run_console = True
        self.vbmc._state = [libvirt.VIR_DOMAIN_SHUTOFF]
        self.vbmc._stream = mock_stream
        ret = self.vbmc.check_console()

        mock_conn.newStream.assert_not_called()
        mock_domain.openConsole.assert_not_called()
        mock_stream.eventRemoveCallback.assert_called()
        self.assertEqual(ret, True)

    def test_check_console_none(self, mock_libvirt_domain,
                                mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_domain = mock.MagicMock()
        mock_stream = mock.MagicMock()
        self.vbmc._conn = mock_conn
        self.vbmc._domain = mock_domain
        self.vbmc._run_console = True
        self.vbmc._state = None
        self.vbmc._stream = None
        ret = self.vbmc.check_console()

        mock_conn.newStream.assert_not_called()
        mock_domain.openConsole.assert_not_called()
        mock_stream.eventAddCallback.assert_not_called()
        mock_stream.eventRemoveCallback.assert_not_called()
        self.assertEqual(ret, True)

    @mock.patch.object(threading.Thread, 'start')
    @mock.patch.object(bmc.Bmc, 'activate_payload')
    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_activate_payload_deactivated(self,
                                          mock_deactivate_payload,
                                          mock_activate_payload,
                                          mock_thread_start,
                                          mock_libvirt_domain,
                                          mock_libvirt_open):
        self.vbmc.activated = False
        self.vbmc.activate_payload('foo', 'bar')

        mock_thread_start.assert_called()
        mock_activate_payload.assert_called_with('foo', 'bar')
        mock_deactivate_payload.assert_not_called()
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    @mock.patch.object(threading.Thread, 'start')
    @mock.patch.object(bmc.Bmc, 'activate_payload')
    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_activate_payload_activated(self,
                                        mock_deactivate_payload,
                                        mock_activate_payload,
                                        mock_thread_start,
                                        mock_libvirt_domain,
                                        mock_libvirt_open):
        self.vbmc.activated = True
        self.vbmc.activate_payload('foo', 'bar')

        mock_thread_start.assert_not_called()
        mock_activate_payload.assert_not_called()
        mock_deactivate_payload.assert_not_called()

    @mock.patch.object(threading.Thread, 'start')
    @mock.patch.object(bmc.Bmc, 'activate_payload')
    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_activate_payload_error(self,
                                    mock_deactivate_payload,
                                    mock_activate_payload,
                                    mock_thread_start,
                                    mock_libvirt_domain,
                                    mock_libvirt_open):
        mock_libvirt_domain.side_effect = libvirt.libvirtError('boom')
        self.vbmc.activated = False
        self.vbmc.activate_payload('foo', 'bar')

        mock_thread_start.assert_not_called()
        mock_activate_payload.assert_called_with('foo', 'bar')
        mock_deactivate_payload.assert_called_with('foo', 'bar')
        self._assert_libvirt_calls(mock_libvirt_domain, mock_libvirt_open)

    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_deactivate_payload_activated(self,
                                          mock_deactivate_payload,
                                          mock_libvirt_domain,
                                          mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_thread = mock.MagicMock()
        self.vbmc.activated = True
        self.vbmc._conn = mock_conn
        self.vbmc._sol_thread = mock_thread
        self.vbmc.deactivate_payload('foo', 'bar')

        mock_thread.join.assert_called()
        mock_conn.close.assert_called()
        mock_deactivate_payload.assert_called_with('foo', 'bar')

    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_deactivate_payload_deactivated(self,
                                            mock_deactivate_payload,
                                            mock_libvirt_domain,
                                            mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_thread = mock.MagicMock()
        self.vbmc._activated = False
        self.vbmc._conn = mock_conn
        self.vbmc._sol_thread = mock_thread
        self.vbmc.deactivate_payload('foo', 'bar')

        mock_thread.join.assert_not_called()
        mock_conn.close.assert_not_called()
        mock_deactivate_payload.assert_not_called()

    @mock.patch.object(bmc.Bmc, 'deactivate_payload')
    def test_deactivate_payload_error(self,
                                      mock_deactivate_payload,
                                      mock_libvirt_domain,
                                      mock_libvirt_open):
        mock_conn = mock.MagicMock()
        mock_thread = mock.MagicMock()
        mock_thread.join.side_effect = libvirt.libvirtError('boom')
        self.vbmc.activated = True
        self.vbmc._conn = mock_conn
        self.vbmc._sol_thread = mock_thread
        self.vbmc.deactivate_payload('foo', 'bar')

        mock_thread.join.assert_called()
        mock_conn.close.assert_called()
        mock_deactivate_payload.assert_not_called()

    def test_lifecycle_callback(self, mock_libvirt_domain, mock_libvirt_open):
        mock_domain = mock.MagicMock()
        mock_domain.state.return_value = [libvirt.VIR_DOMAIN_RUNNING]
        self.vbmc._state = None
        self.vbmc._domain = mock_domain
        vbmc.lifecycle_callback(None, None, None, None, self.vbmc)
        self.assertEqual(self.vbmc.state, [libvirt.VIR_DOMAIN_RUNNING])

    @mock.patch.object(vbmc.LOG, 'error')
    def test_error_handler_ignore(self, mock_error, mock_libvirt_domain,
                                  mock_libvirt_open):
        vbmc.error_handler(None,
                           (libvirt.VIR_ERR_RPC, libvirt.VIR_FROM_STREAMS))
        mock_error.assert_not_called()

    @mock.patch.object(vbmc.LOG, 'error')
    def test_error_handler_error(self, mock_error, mock_libvirt_domain,
                                 mock_libvirt_open):
        vbmc.error_handler(None,
                           (libvirt.VIR_ERR_ERROR, libvirt.VIR_FROM_STREAMS))
        mock_error.assert_called()

    def test_stream_callback(self, mock_libvirt_domain, mock_libvirt_open):
        mock_stream = mock.MagicMock()
        mock_sol = mock.MagicMock()
        mock_stream.recv.return_value = 'foo'
        self.vbmc.sol = mock_sol
        self.vbmc._stream = mock_stream
        vbmc.stream_callback(None, None, self.vbmc)
        mock_sol.send_data.assert_called_with('foo')

    def test_stream_callback_error(self, mock_libvirt_domain,
                                   mock_libvirt_open):
        mock_stream = mock.MagicMock()
        mock_stream.recv.side_effect = libvirt.libvirtError('boom')
        mock_sol = mock.MagicMock()
        self.vbmc.sol = mock_sol
        self.vbmc._stream = mock_stream
        vbmc.stream_callback(None, None, self.vbmc)
        mock_sol.send_data.assert_not_called()
