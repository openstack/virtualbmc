# Copyright 2017 Red Hat, Inc.
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

import json
import os
from unittest import mock

import zmq

from virtualbmc import control
from virtualbmc.tests.unit import base


class VBMCControlServerTestCase(base.TestCase):

    @mock.patch.object(zmq, 'Context')
    @mock.patch.object(zmq, 'Poller')
    @mock.patch.object(os, 'path')
    @mock.patch.object(os, 'remove')
    def test_control_loop(self, mock_rm, mock_path, mock_zmq_poller,
                          mock_zmq_context):
        mock_path.exists.return_value = False

        mock_vbmc_manager = mock.MagicMock()
        mock_handle_command = mock.MagicMock()

        req = {
            'command': 'list',
        }

        mock_zmq_context = mock_zmq_context.return_value
        mock_zmq_socket = mock_zmq_context.socket.return_value
        mock_zmq_socket.recv.return_value = json.dumps(req).encode()
        mock_zmq_poller = mock_zmq_poller.return_value
        mock_zmq_poller.poll.return_value = {
            mock_zmq_socket: zmq.POLLIN
        }

        rsp = {
            'rc': 0,
            'msg': ['OK']
        }

        class QuitNow(Exception):
            pass

        mock_handle_command.return_value = rsp
        mock_zmq_socket.send.side_effect = QuitNow()

        self.assertRaises(QuitNow,
                          control.main_loop,
                          mock_vbmc_manager, mock_handle_command)

        mock_zmq_socket.bind.assert_called_once()
        mock_handle_command.assert_called_once()

        response = json.loads(mock_zmq_socket.send.call_args[0][0].decode())

        self.assertEqual(rsp, response)
