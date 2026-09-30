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

import struct
from unittest import mock

import libvirt

from virtualbmc import exception
from virtualbmc import sol
from virtualbmc.tests.unit import base
from virtualbmc.tests.unit import utils as test_utils
from virtualbmc import vbmc


class ServerConsoleTestCase(base.TestCase):

    def setUp(self):
        super(ServerConsoleTestCase, self).setUp()
        self.session = mock.Mock(spec=['sol_handler', 'send_payload'])
        self.handler = mock.Mock()
        self.console = sol.ServerConsole(self.session, self.handler)

    def test_activation_does_not_reenter_ipmi_event_loop(self):
        with mock.patch.object(sol.console.session.Session,
                               'wait_for_rsp') as wait:
            sol.ServerConsole(self.session, self.handler)
        wait.assert_not_called()

    def test_lost_ack_cleanup_does_not_require_client_session_fields(self):
        self.console._print_error('Connection lost')
        self.assertIsNone(self.session.sol_handler)
        self.assertIsNone(self.console.ipmi_session)
        self.assertTrue(self.console.broken)
        self.assertFalse(self.console.activated)
        self.handler.assert_called_once_with(
            self.console, {'error': 'Connection lost'})

    def test_output_send_error_closes_transport(self):
        self.session.send_payload.side_effect = OSError('disconnected')
        self.console.send_data(b'output')
        self.assertFalse(self.console.awaitingack)
        self.assertIsNone(self.session.sol_handler)
        self.handler.assert_called_once_with(
            self.console, {'error': 'disconnected'})

    def test_input_ack_error_closes_transport(self):
        self.session.send_payload.side_effect = OSError('disconnected')
        self.console._got_sol_payload(bytearray([1, 0, 0, 0]) + b'input')
        self.assertTrue(self.console.broken)
        self.assertIsNone(self.session.sol_handler)

    def test_output_is_split_into_acknowledgeable_packets(self):
        def acknowledge(payload, **kwargs):
            self.console._got_sol_payload(
                bytearray([0, payload[0], len(payload) - 4, 0]))

        self.session.send_payload.side_effect = acknowledge
        data = bytes(range(256))
        self.console.send_data(data)
        packets = [call.args[0]
                   for call in self.session.send_payload.call_args_list]
        self.assertEqual([259, 5], [len(packet) for packet in packets])
        self.assertEqual(data, b''.join(packet[4:] for packet in packets))
        self.assertFalse(self.console.awaitingack)

    def test_close_cancels_output_and_notifies_once(self):
        self.console.awaitingack = True
        self.console.pendingoutput = [b'pending']
        self.console.close()
        self.console.close()
        self.console.send_payload(bytearray([1, 0, 0, 0]) + b'stale')
        self.assertFalse(self.console.awaitingack)
        self.assertEqual([], self.console.pendingoutput)
        self.assertIsNone(self.session.sol_handler)
        self.session.send_payload.assert_called_once_with(
            bytearray([0, 0, 0, 0x10]), payload_type=1, retry=False)

    def test_close_does_not_detach_replacement_console(self):
        replacement = sol.ServerConsole(self.session, mock.Mock())
        self.console.close()
        self.assertEqual(replacement._got_sol_payload,
                         self.session.sol_handler)
        self.session.send_payload.assert_not_called()

    def test_close_handles_notification_failure(self):
        self.session.send_payload.side_effect = OSError('disconnected')
        self.console.close()
        self.assertIsNone(self.console.ipmi_session)
        self.assertIsNone(self.session.sol_handler)

    def test_malformed_payloads_are_ignored(self):
        for payload in (b'', b'\x01\x00', b'x' * 260):
            self.console._got_sol_payload(payload)
        self.handler.assert_not_called()
        self.session.send_payload.assert_not_called()


class LibvirtConsoleTestCase(base.TestCase):

    def setUp(self):
        super(LibvirtConsoleTestCase, self).setUp()
        patch = mock.patch.object(sol.time, 'monotonic', return_value=100)
        self.clock = patch.start()
        self.addCleanup(patch.stop)
        self.context = mock.MagicMock()
        self.conn = self.context.__enter__.return_value
        self.domain = self.conn.lookupByName.return_value
        self.domain.XMLDesc.return_value = (
            '<domain><devices><console type="pty"/></devices></domain>')
        self.domain.isActive.return_value = True
        self.stream = self.conn.newStream.return_value
        self.stream.recv.return_value = -2
        self.patch = mock.patch.object(sol.utils, 'libvirt_open',
                                       return_value=self.context)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.console = sol.LibvirtConsole('node', {'uri': 'qemu:///system'})
        self.addCleanup(self.console.close)

    def test_bidirectional_data_and_safe_attach(self):
        self.console.open()
        self.domain.openConsole.assert_called_once_with(
            None, self.stream, libvirt.VIR_DOMAIN_CONSOLE_SAFE)
        self.stream.send.return_value = 3
        self.stream.recv.return_value = b'login: '
        self.console.write(b'abc')
        self.assertEqual(b'login: ', self.console.poll())
        self.stream.send.assert_called_once_with(b'abc')
        self.stream.recv.assert_called_once_with(255)

    def test_partial_write_and_would_block_preserve_input(self):
        self.console.open()
        self.console.write(b'abcdef')
        self.stream.send.side_effect = [2, -2, 4]
        for _ in range(4):
            self.assertEqual(b'', self.console.poll())
        self.assertEqual([mock.call(b'abcdef'), mock.call(b'cdef'),
                          mock.call(b'cdef')], self.stream.send.call_args_list)

    def test_activate_off_then_attach_when_powered_on(self):
        self.domain.isActive.return_value = False
        self.console.open()
        self.console.write(b'do not replay this')
        self.conn.newStream.assert_not_called()
        self.domain.isActive.return_value = True
        self.console.poll()
        self.domain.openConsole.assert_called_once()
        self.stream.send.assert_not_called()

    def test_eof_reconnect_drops_old_input(self):
        self.console.open()
        self.console.write(b'old input')
        self.stream.send.return_value = -2
        self.stream.recv.return_value = b''
        self.console.poll()
        self.stream.abort.assert_called_once()
        self.context.__exit__.assert_called_once()
        new_stream = mock.Mock()
        new_stream.recv.return_value = b'new boot'
        self.conn.newStream.return_value = new_stream
        self.clock.return_value += sol.RECONNECT_INTERVAL
        self.assertEqual(b'new boot', self.console.poll())
        new_stream.send.assert_not_called()

    def test_console_busy_cleans_up(self):
        self.domain.openConsole.side_effect = libvirt.libvirtError('busy')
        self.assertRaises(libvirt.libvirtError, self.console.open)
        self.stream.abort.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_missing_console_rejected_even_when_off(self):
        self.domain.XMLDesc.return_value = '<domain><devices/></domain>'
        self.domain.isActive.return_value = False
        self.assertRaises(exception.ConsoleNotFound, self.console.open)
        self.context.__exit__.assert_called_once()

    def test_input_is_bounded(self):
        self.console.open()
        self.console.write(b'x' * sol.MAX_PENDING_INPUT)
        self.assertRaises(BufferError, self.console.write, b'x')

    def test_close_is_idempotent(self):
        self.console.open()
        self.console.close()
        self.console.close()
        self.stream.abort.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_open_failure_closes_connection(self):
        self.conn.lookupByName.side_effect = libvirt.libvirtError('no domain')
        self.assertRaises(exception.DomainNotFound, self.console.open)
        self.context.__exit__.assert_called_once()

    def test_failed_reconnect_is_rate_limited(self):
        self.domain.openConsole.side_effect = libvirt.libvirtError('busy')
        self.console.poll()
        self.console.poll()
        self.domain.openConsole.assert_called_once()
        self.clock.return_value += sol.RECONNECT_INTERVAL
        self.console.poll()
        self.assertEqual(2, self.domain.openConsole.call_count)

    def test_reconnect_does_not_hide_programming_errors(self):
        self.domain.isActive.side_effect = RuntimeError('unexpected')
        self.assertRaises(RuntimeError, self.console.poll)
        self.context.__exit__.assert_called_once()

    def test_stream_error_releases_connection(self):
        self.console.open()
        self.stream.recv.side_effect = libvirt.libvirtError('connection lost')
        self.assertEqual(b'', self.console.poll())
        self.stream.abort.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_abort_error_still_releases_connection(self):
        self.console.open()
        self.stream.abort.side_effect = libvirt.libvirtError('already closed')
        self.console.close()
        self.context.__exit__.assert_called_once()


class SOLPayloadTestCase(base.TestCase):

    def setUp(self):
        super(SOLPayloadTestCase, self).setUp()
        patch = mock.patch.object(sol.time, 'monotonic', return_value=100)
        self.clock = patch.start()
        self.addCleanup(patch.stop)
        with mock.patch('pyghmi.ipmi.bmc.Bmc.__init__', return_value=None):
            self.bmc = vbmc.VirtualBMC(**test_utils.get_domain())
        self.bmc.port = 6230
        self.request = {'data': [1, 1, 0xc0, 0, 0, 0]}
        self.session = mock.Mock()
        patch = mock.patch.object(sol, 'LibvirtConsole')
        self.bridge = patch.start().return_value
        self.addCleanup(patch.stop)
        patch = mock.patch.object(sol, 'ServerConsole')
        self.server_class = patch.start()
        self.addCleanup(patch.stop)
        self.server = self.server_class.return_value
        self.server.ipmi_session = self.session
        self.server.activated = True
        self.server.broken = False
        self.server.last_activity = self.clock.return_value
        self.addCleanup(self.bmc._close_sol)

    def activate(self):
        self.bmc.activate_payload(self.request, self.session)

    def test_activation_response_sizes_and_nondefault_port(self):
        self.activate()
        data = self.session.send_ipmi_response.call_args.kwargs['data']
        self.assertEqual(12, len(data))
        self.assertEqual((259, 259, 6230),
                         struct.unpack('<HHH', bytes(data[4:10])))
        self.assertIs(self.server, self.bmc.sol)

    def test_input_immediately_after_activation_response(self):
        self.session.send_ipmi_response.side_effect = (
            lambda **kwargs: self.bmc._sol_input(self.server, b'first'))
        self.activate()
        self.bridge.write.assert_called_once_with(b'first')

    def test_second_client_is_rejected_without_replacing_first(self):
        self.activate()
        second = mock.Mock()
        self.bmc.activate_payload(self.request, second)
        second.send_ipmi_response.assert_called_once_with(code=0x80)
        self.bridge.open.assert_called_once()
        self.bridge.close.assert_not_called()

    def test_failed_open_can_be_retried(self):
        self.bridge.open.side_effect = [
            exception.ConsoleNotFound(domain='node'), None]
        self.activate()
        self.assertIsNone(self.bmc.sol)
        self.session.send_ipmi_response.assert_called_with(code=0x81)
        self.activate()
        self.assertIs(self.server, self.bmc.sol)

    def test_deactivate_from_another_session_releases_console(self):
        self.activate()
        second = mock.Mock()
        self.bmc.deactivate_payload(self.request, second)
        second.send_ipmi_response.assert_called_once_with()
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)
        self.server.close.assert_called_once_with()
        self.bmc.deactivate_payload(self.request, second)
        second.send_ipmi_response.assert_called_with(code=0x80)

    def test_idle_session_expires_and_allows_new_client(self):
        self.activate()
        self.server.last_activity -= sol.IDLE_TIMEOUT + 1
        self.activate()
        self.bridge.close.assert_called_once()
        self.assertEqual(2, self.bridge.open.call_count)

    def test_keepalive_refreshes_only_owning_session(self):
        self.activate()
        self.server.last_activity = 0
        request = {'netfn': 6, 'command': 1, 'data': []}
        with mock.patch.object(vbmc.bmc.Bmc, 'handle_raw_request'):
            self.bmc.handle_raw_request(request, mock.Mock())
            self.assertEqual(0, self.server.last_activity)
            self.bmc.handle_raw_request(request, self.session)
        self.assertEqual(self.clock.return_value, self.server.last_activity)

    def test_transport_error_releases_console(self):
        self.activate()
        self.server.broken = True
        self.server.ipmi_session = None
        callback = self.server_class.call_args.args[1]
        callback(self.server, {'error': 'Connection lost'})
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_malformed_or_unsupported_payload_rejected(self):
        for data in ([], [1], [2, 1, 0, 0, 0, 0], [1, 2, 0, 0, 0, 0]):
            self.bmc.activate_payload({'data': data}, self.session)
            self.session.send_ipmi_response.assert_called_with(code=0xcc)
        self.bridge.open.assert_not_called()

    def test_input_overflow_disconnects_client(self):
        self.activate()
        self.bridge.write.side_effect = BufferError
        self.bmc._sol_input(self.server, b'input')
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_failed_activation_response_releases_console(self):
        self.session.send_ipmi_response.side_effect = OSError('disconnected')
        self.assertRaises(OSError, self.activate)
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_failed_deactivation_response_releases_console(self):
        self.activate()
        self.session.send_ipmi_response.side_effect = OSError('disconnected')
        self.assertRaises(OSError, self.bmc.deactivate_payload,
                          self.request, self.session)
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_unexpected_close_error_still_releases_bridge(self):
        self.activate()
        self.server.close.side_effect = RuntimeError('unexpected')
        self.assertRaises(RuntimeError, self.bmc._close_sol)
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_callback_from_previous_console_is_ignored(self):
        self.activate()
        old_console = mock.Mock(broken=True)
        self.bmc._sol_input(old_console, {'error': 'Connection lost'})
        self.bmc._sol_input(old_console, b'stale input')
        self.bridge.close.assert_not_called()
        self.bridge.write.assert_not_called()

    def test_output_error_releases_only_sol(self):
        self.activate()
        self.bridge.poll.return_value = b'output'
        self.server.send_data.side_effect = OSError('disconnected')
        self.bmc._poll_sol()
        self.bridge.close.assert_called_once()
        self.assertIsNone(self.bmc.sol)

    def test_old_output_error_does_not_close_new_console(self):
        self.activate()
        replacement = mock.Mock()

        def replace_console(data):
            self.bmc.sol = replacement
            raise OSError('old session disconnected')

        self.bridge.poll.return_value = b'output'
        self.server.send_data.side_effect = replace_console
        self.bmc._poll_sol()
        self.assertIs(replacement, self.bmc.sol)
        self.bridge.close.assert_not_called()

    def test_listen_services_both_event_loops_and_cleans_up(self):
        self.activate()
        self.bridge.poll.return_value = b'output'
        with mock.patch.multiple(vbmc.libvirt,
                                 virEventRegisterDefaultImpl=mock.DEFAULT,
                                 virEventAddTimeout=mock.DEFAULT,
                                 virEventRunDefaultImpl=mock.DEFAULT,
                                 virEventRemoveTimeout=mock.DEFAULT) as events:
            with mock.patch.object(vbmc.ipmi_session.Session, 'wait_for_rsp',
                                   side_effect=[None, KeyboardInterrupt]):
                self.assertRaises(KeyboardInterrupt, self.bmc.listen)
        events['virEventRunDefaultImpl'].assert_called_once()
        events['virEventRemoveTimeout'].assert_called_once_with(
            events['virEventAddTimeout'].return_value)
        self.server.send_data.assert_called_once_with(b'output')
        self.bridge.close.assert_called_once()
