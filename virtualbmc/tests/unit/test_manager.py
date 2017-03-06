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

import copy
import errno
import os
import shutil
import signal

import mock
from six.moves import builtins
from six.moves import configparser

from virtualbmc import exception
from virtualbmc import manager
from virtualbmc.tests.unit import base
from virtualbmc.tests.unit import utils as test_utils
from virtualbmc import utils

_CONFIG_PATH = '/foo'


class VirtualBMCManagerTestCase(base.TestCase):

    def setUp(self):
        super(VirtualBMCManagerTestCase, self).setUp()
        self.manager = manager.VirtualBMCManager()
        self.manager.config_dir = _CONFIG_PATH
        self.domain0 = test_utils.get_domain()
        self.domain1 = test_utils.get_domain(domain_name='Patrick', port=321)
        self.domain_name0 = self.domain0['domain_name']
        self.domain_name1 = self.domain1['domain_name']
        self.domain_path0 = os.path.join(_CONFIG_PATH, self.domain_name0)
        self.domain_path1 = os.path.join(_CONFIG_PATH, self.domain_name1)
        self.add_params = {'username': 'admin', 'password': 'pass',
                           'port': '777', 'address': '::',
                           'domain_name': 'Squidward Tentacles',
                           'libvirt_uri': 'foo://bar',
                           'libvirt_sasl_username': 'sasl_admin',
                           'libvirt_sasl_password': 'sasl_pass'}

    def _get_config(self, section, item):
        return self.domain0.get(item)

    @mock.patch.object(os.path, 'exists')
    @mock.patch.object(configparser, 'ConfigParser')
    def test__parse_config(self, mock_configparser, mock_exists):
        mock_exists.return_value = True
        config = mock_configparser.return_value
        config.get.side_effect = self._get_config
        config.getint.side_effect = self._get_config
        ret = self.manager._parse_config(self.domain_name0)

        self.assertEqual(self.domain0, ret)
        config.getint.assert_called_once_with('VirtualBMC', 'port')
        mock_configparser.assert_called_once_with()

        expected_get_calls = [mock.call('VirtualBMC', i)
                              for i in ('username', 'password', 'address',
                                        'domain_name', 'libvirt_uri',
                                        'libvirt_sasl_username',
                                        'libvirt_sasl_password')]
        self.assertEqual(expected_get_calls, config.get.call_args_list)

    @mock.patch.object(os.path, 'exists')
    def test__parse_config_domain_not_found(self, mock_exists):
        mock_exists.return_value = False
        self.assertRaises(exception.DomainNotFound,
                          self.manager._parse_config, self.domain_name0)
        mock_exists.assert_called_once_with(self.domain_path0 + '/config')

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(utils, 'is_pid_running')
    @mock.patch.object(manager.VirtualBMCManager, '_parse_config')
    def _test__show(self, mock__parse, mock_pid, mock_open, expected=None):
        mock_pid.return_value = True
        mock__parse.return_value = self.domain0
        f = mock.MagicMock()
        f.read.return_value = self.domain0['port']
        mock_open.return_value.__enter__.return_value = f

        if expected is None:
            expected = self.domain0.copy()
            expected['status'] = manager.RUNNING

        ret = self.manager._show(self.domain_name0)
        self.assertEqual(expected, ret)

    def test__show(self):
        conf = {'default': {'show_passwords': True}}
        with mock.patch('virtualbmc.manager.CONF', conf):
            self._test__show()

    def test__show_mask_passwords(self):
        conf = {'default': {'show_passwords': False}}
        with mock.patch('virtualbmc.manager.CONF', conf):
            expected = self.domain0.copy()
            expected['password'] = '***'
            expected['libvirt_sasl_password'] = '***'
            expected['status'] = manager.RUNNING
            self._test__show(expected=expected)

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(configparser, 'ConfigParser')
    @mock.patch.object(os, 'makedirs')
    @mock.patch.object(utils, 'check_libvirt_connection_and_domain')
    def test_add(self, mock_check_conn, mock_makedirs, mock_configparser,
                 mock_open):
        config = mock_configparser.return_value
        params = copy.copy(self.add_params)
        self.manager.add(**params)

        expected_calls = [mock.call('VirtualBMC', i, self.add_params[i])
                          for i in self.add_params]
        self.assertEqual(sorted(expected_calls),
                         sorted(config.set.call_args_list))
        config.add_section.assert_called_once_with('VirtualBMC')
        config.write.assert_called_once_with(mock.ANY)
        mock_check_conn.assert_called_once_with(
            self.add_params['libvirt_uri'], self.add_params['domain_name'],
            sasl_username=self.add_params['libvirt_sasl_username'],
            sasl_password=self.add_params['libvirt_sasl_password'])
        mock_makedirs.assert_called_once_with(
            os.path.join(_CONFIG_PATH, self.add_params['domain_name']))
        mock_configparser.assert_called_once_with()

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(configparser, 'ConfigParser')
    @mock.patch.object(os, 'makedirs')
    @mock.patch.object(utils, 'check_libvirt_connection_and_domain')
    def test_add_with_port_as_int(self, mock_check_conn, mock_makedirs,
                                  mock_configparser, mock_open):
        config = mock_configparser.return_value
        params = copy.copy(self.add_params)
        params['port'] = int(params['port'])
        self.manager.add(**params)

        expected_calls = [mock.call('VirtualBMC', i, self.add_params[i])
                          for i in self.add_params]
        self.assertEqual(sorted(expected_calls),
                         sorted(config.set.call_args_list))
        config.add_section.assert_called_once_with('VirtualBMC')
        config.write.assert_called_once_with(mock.ANY)
        mock_check_conn.assert_called_once_with(
            self.add_params['libvirt_uri'], self.add_params['domain_name'],
            sasl_username=self.add_params['libvirt_sasl_username'],
            sasl_password=self.add_params['libvirt_sasl_password'])
        mock_makedirs.assert_called_once_with(
            os.path.join(_CONFIG_PATH, self.add_params['domain_name']))
        mock_configparser.assert_called_once_with()

    @mock.patch.object(os, 'makedirs')
    @mock.patch.object(utils, 'check_libvirt_connection_and_domain')
    def test_add_domain_already_exist(self, mock_check_conn, mock_makedirs):
        os_error = OSError()
        os_error.errno = errno.EEXIST
        mock_makedirs.side_effect = os_error

        self.assertRaises(exception.DomainAlreadyExists,
                          self.manager.add, **self.add_params)
        mock_check_conn.assert_called_once_with(
            self.add_params['libvirt_uri'], self.add_params['domain_name'],
            sasl_username=self.add_params['libvirt_sasl_username'],
            sasl_password=self.add_params['libvirt_sasl_password'])

    @mock.patch.object(os, 'makedirs')
    @mock.patch.object(utils, 'check_libvirt_connection_and_domain')
    def test_add_oserror(self, mock_check_conn, mock_makedirs):
        mock_makedirs.side_effect = OSError

        self.assertRaises(exception.VirtualBMCError,
                          self.manager.add, **self.add_params)
        mock_check_conn.assert_called_once_with(
            self.add_params['libvirt_uri'], self.add_params['domain_name'],
            sasl_username=self.add_params['libvirt_sasl_username'],
            sasl_password=self.add_params['libvirt_sasl_password'])

    @mock.patch.object(shutil, 'rmtree')
    @mock.patch.object(os.path, 'exists')
    @mock.patch.object(manager.VirtualBMCManager, 'stop')
    def test_delete(self, mock_stop, mock_exists, mock_rmtree):
        mock_exists.return_value = True
        self.manager.delete(self.domain_name0)

        mock_exists.assert_called_once_with(self.domain_path0)
        mock_stop.assert_called_once_with(self.domain_name0)
        mock_rmtree.assert_called_once_with(self.domain_path0)

    @mock.patch.object(os.path, 'exists')
    def test_delete_domain_not_found(self, mock_exists):
        mock_exists.return_value = False
        self.assertRaises(exception.DomainNotFound,
                          self.manager.delete, self.domain_name0)
        mock_exists.assert_called_once_with(self.domain_path0)

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(manager, 'VirtualBMC')
    @mock.patch.object(utils, 'detach_process')
    @mock.patch.object(utils, 'check_libvirt_connection_and_domain')
    @mock.patch.object(manager.VirtualBMCManager, '_parse_config')
    @mock.patch.object(os.path, 'exists')
    def test_start(self, mock_exists, mock__parse, mock_check_conn,
                   mock_detach, mock_vbmc, mock_open):
        conf = {'ipmi': {'session_timeout': 10},
                'default': {'show_passwords': False}}
        with mock.patch('virtualbmc.manager.CONF', conf):
            mock_exists.return_value = True
            mock__parse.return_value = self.domain0
            mock_detach.return_value.__enter__.return_value = 99999
            file_handler = mock_open.return_value.__enter__.return_value
            self.manager.start(self.domain_name0)

            mock_exists.assert_called_once_with(self.domain_path0)
            mock__parse.assert_called_once_with(self.domain_name0)
            mock_check_conn.assert_called_once_with(
                self.domain0['libvirt_uri'], self.domain0['domain_name'],
                sasl_username=self.domain0['libvirt_sasl_username'],
                sasl_password=self.domain0['libvirt_sasl_password'])
            mock_detach.assert_called_once_with()
            mock_vbmc.assert_called_once_with(**self.domain0)
            mock_vbmc.return_value.listen.assert_called_once_with(timeout=10)
            file_handler.write.assert_called_once_with('99999')

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(os, 'kill')
    @mock.patch.object(os, 'remove')
    @mock.patch.object(os.path, 'exists')
    def test_stop(self, mock_exists, mock_remove, mock_kill, mock_open):
        mock_exists.return_value = True
        f = mock.MagicMock()
        f.read.return_value = self.domain0['port']
        mock_open.return_value.__enter__.return_value = f

        self.manager.stop(self.domain_name0)
        f.read.assert_called_once_with()
        mock_exists.assert_called_once_with(self.domain_path0)
        mock_remove.assert_called_once_with(self.domain_path0 + '/pid')
        mock_kill.assert_called_once_with(self.domain0['port'],
                                          signal.SIGKILL)

    @mock.patch.object(os.path, 'exists')
    def test_stop_domain_not_found(self, mock_exists):
        mock_exists.return_value = False
        self.assertRaises(exception.DomainNotFound,
                          self.manager.stop, self.domain_name0)
        mock_exists.assert_called_once_with(self.domain_path0)

    @mock.patch.object(builtins, 'open')
    @mock.patch.object(os.path, 'exists')
    def test_stop_pid_file_not_found(self, mock_exists, mock_open):
        mock_exists.return_value = True
        f = mock.MagicMock()
        f.read.return_value = self.domain0['port']
        mock_open.return_value.__enter__.side_effect = IOError('boom')

        self.assertRaises(exception.VirtualBMCError,
                          self.manager.stop, self.domain_name0)

    @mock.patch.object(os.path, 'isdir')
    @mock.patch.object(os, 'listdir')
    @mock.patch.object(manager.VirtualBMCManager, '_show')
    def test_list(self, mock__show, mock_listdir, mock_isdir):
        mock_isdir.return_value = True
        mock_listdir.return_value = (self.domain_name0, self.domain_name1)
        expected_ret = [self.domain0, self.domain1]
        mock__show.side_effect = expected_ret
        ret = self.manager.list()

        self.assertEqual(expected_ret, ret)
        mock_listdir.assert_called_once_with(_CONFIG_PATH)

        expected_calls = [mock.call(self.domain_path0),
                          mock.call(self.domain_path1)]
        self.assertEqual(expected_calls, mock_isdir.call_args_list)

    @mock.patch.object(manager.VirtualBMCManager, '_show')
    def test_show(self, mock__show):
        self.manager.show(self.domain0)
        mock__show.assert_called_once_with(self.domain0)
