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

import builtins
import os
from unittest import mock


from virtualbmc.cmd import vbmcd
from virtualbmc import control
from virtualbmc.tests.unit import base
from virtualbmc import utils


class VBMCDTestCase(base.TestCase):

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(os, 'kill')
    @mock.patch.object(os, 'unlink')
    def test_main_foreground(self, mock_unlink, mock_kill, mock_open):
        with mock.patch.object(control, 'application') as mock_ml:
            mock_kill.side_effect = OSError()
            vbmcd.main(['--foreground'])
            mock_kill.assert_called_once()
            mock_ml.assert_called_once()
            mock_unlink.assert_called_once()

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(os, 'kill')
    @mock.patch.object(os, 'unlink')
    def test_main_background(self, mock_unlink, mock_kill, mock_open):
        with mock.patch.object(utils, 'detach_process') as mock_dp:
            with mock.patch.object(control, 'application') as mock_ml:
                mock_kill.side_effect = OSError()
                mock_dp.return_value.__enter__.return_value = 0
                vbmcd.main([])
                mock_kill.assert_called_once()
                mock_dp.assert_called_once()
                mock_ml.assert_called_once()
                mock_unlink.assert_called_once()
