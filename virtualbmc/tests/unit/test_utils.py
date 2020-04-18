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

import os
from unittest import mock

import libvirt

from virtualbmc import exception
from virtualbmc.tests.unit import base
from virtualbmc import utils


class MiscUtilsTestCase(base.TestCase):

    @mock.patch.object(os, 'kill')
    def test_is_pid_running(self, mock_kill):
        self.assertTrue(utils.is_pid_running(123))
        mock_kill.assert_called_once_with(123, 0)

    @mock.patch.object(os, 'kill')
    def test_is_pid_running_not_running(self, mock_kill):
        mock_kill.side_effect = OSError('boom')
        self.assertFalse(utils.is_pid_running(123))
        mock_kill.assert_called_once_with(123, 0)

    def test_str2bool(self):
        for b in ('TRUE', 'true', 'True'):
            self.assertTrue(utils.str2bool(b))

        for b in ('FALSE', 'false', 'False'):
            self.assertFalse(utils.str2bool(b))

        self.assertRaises(ValueError, utils.str2bool, 'bogus value')

    def test_mask_dict_password(self):
        input_dict = {'foo': 'bar', 'password': 'SpongeBob SquarePants'}
        output_dict = utils.mask_dict_password(input_dict)
        expected = {'foo': 'bar', 'password': '***'}
        self.assertEqual(expected, output_dict)


class LibvirtUtilsTestCase(base.TestCase):

    def setUp(self):
        super(LibvirtUtilsTestCase, self).setUp()
        self.fake_connection = mock.Mock()
        self.uri = 'fake:///patrick'

    def test_get_libvirt_domain(self):
        self.fake_connection.lookupByName.return_value = 'fake connection'
        ret = utils.get_libvirt_domain(self.fake_connection, 'SpongeBob')

        self.fake_connection.lookupByName.assert_called_once_with('SpongeBob')
        self.assertEqual('fake connection', ret)

    def test_get_libvirt_domain_not_found(self):
        self.fake_connection.lookupByName.side_effect = libvirt.libvirtError(
            'boom')
        self.assertRaises(exception.DomainNotFound, utils.get_libvirt_domain,
                          self.fake_connection, 'Fred')
        self.fake_connection.lookupByName.assert_called_once_with('Fred')

    def _test_libvirt_open(self, mock_open, **kwargs):
        mock_open.return_value = self.fake_connection
        with utils.libvirt_open(self.uri, **kwargs) as conn:
            self.assertEqual(self.fake_connection, conn)

        self.fake_connection.close.assert_called_once_with()

    @mock.patch.object(libvirt, 'open')
    def test_libvirt_open(self, mock_open):
        self._test_libvirt_open(mock_open)
        mock_open.assert_called_once_with(self.uri)

    @mock.patch.object(libvirt, 'open')
    def test_libvirt_open_error(self, mock_open):
        mock_open.side_effect = libvirt.libvirtError('boom')
        self.assertRaises(exception.LibvirtConnectionOpenError,
                          self._test_libvirt_open, mock_open)
        mock_open.assert_called_once_with(self.uri)

    @mock.patch.object(libvirt, 'openReadOnly')
    def test_libvirt_open_readonly(self, mock_open):
        self._test_libvirt_open(mock_open, readonly=True)
        mock_open.assert_called_once_with(self.uri)

    @mock.patch.object(libvirt, 'openAuth')
    def _test_libvirt_open_sasl(self, mock_open, readonly=False):
        username = 'Eugene H. Krabs'
        password = ('hamburger, fresh lettuce, crisp onions, tomatoes, '
                    'undersea cheese, pickles, mustard and ketchup')
        self._test_libvirt_open(mock_open, sasl_username=username,
                                sasl_password=password, readonly=readonly)
        ro = 1 if readonly else 0
        mock_open.assert_called_once_with(self.uri, mock.ANY, ro)

    def test_libvirt_open_sasl(self):
        self._test_libvirt_open_sasl()

    def test_libvirt_open_sasl_readonly(self):
        self._test_libvirt_open_sasl(readonly=True)


@mock.patch.object(utils, 'os')
class DetachProcessUtilsTestCase(base.TestCase):

    def test_detach_process(self, mock_os):

        # 2nd value > 0 so _exit get called and we can assert that we've
        # killed the parent's process
        mock_os.fork.side_effect = (0, 999)
        mock_os.devnull = os.devnull

        with utils.detach_process() as pid:
            self.assertEqual(0, pid)

        # assert fork() has been called twice
        expected_fork_calls = [mock.call()] * 2
        self.assertEqual(expected_fork_calls, mock_os.fork.call_args_list)

        mock_os.setsid.assert_called_once_with()
        mock_os.chdir.assert_called_once_with('/')
        mock_os.umask.assert_called_once_with(0)
        mock_os._exit.assert_called_once_with(0)

    def test_detach_process_fork_fail(self, mock_os):
        error_msg = 'Kare-a-tay!'
        mock_os.fork.side_effect = OSError(error_msg)

        with self.assertRaisesRegex(exception.DetachProcessError, error_msg):
            with utils.detach_process():
                pass

        mock_os.fork.assert_called_once_with()
        self.assertFalse(mock_os.setsid.called)
        self.assertFalse(mock_os.chdir.called)
        self.assertFalse(mock_os.umask.called)
        self.assertFalse(mock_os._exit.called)

    def test_detach_process_chdir_fail(self, mock_os):
        # 2nd value > 0 so _exit get called and we can assert that we've
        # killed the parent's process
        mock_os.fork.side_effect = (0, 999)

        error_msg = 'Fish paste!'
        mock_os.chdir.side_effect = Exception(error_msg)

        with self.assertRaisesRegex(exception.DetachProcessError, error_msg):
            with utils.detach_process():
                pass

        # assert fork() has been called twice
        expected_fork_calls = [mock.call()] * 2
        self.assertEqual(expected_fork_calls, mock_os.fork.call_args_list)

        mock_os.setsid.assert_called_once_with()
        mock_os.chdir.assert_called_once_with('/')
        mock_os._exit.assert_called_once_with(0)
        self.assertFalse(mock_os.umask.called)

    def test_detach_process_umask_fail(self, mock_os):
        # 2nd value > 0 so _exit get called and we can assert that we've
        # killed the parent's process
        mock_os.fork.side_effect = (0, 999)

        error_msg = 'Barnacles!'
        mock_os.umask.side_effect = Exception(error_msg)

        with self.assertRaisesRegex(exception.DetachProcessError, error_msg):
            with utils.detach_process():
                pass

        # assert fork() has been called twice
        expected_fork_calls = [mock.call()] * 2
        self.assertEqual(expected_fork_calls, mock_os.fork.call_args_list)

        mock_os.setsid.assert_called_once_with()
        mock_os.chdir.assert_called_once_with('/')
        mock_os._exit.assert_called_once_with(0)
        mock_os.umask.assert_called_once_with(0)
