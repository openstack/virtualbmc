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

from six.moves import configparser

from virtualbmc import utils

__all__ = ['get_config']

_CONFIG_FILE_PATHS = (
    os.path.join(os.path.expanduser('~'), '.vbmc', 'virtualbmc.conf'),
    '/etc/virtualbmc/virtualbmc.conf')

CONFIG = None
CONFIG_FILE = ''
for config in _CONFIG_FILE_PATHS:
    if os.path.exists(config):
        CONFIG_FILE = config
        break


class VirtualBMCConfig(object):

    DEFAULTS = {
        'default': {
            'show_passwords': 'false',
            'config_dir': os.path.join(os.path.expanduser('~'), '.vbmc'),
        },
        'log': {
            'logfile': None,
            'debug': 'false'
        },
        'ipmi': {
            # Maximum time (in seconds) to wait for the data to come across
            'session_timeout': 1
        },
    }

    def initialize(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        self._conf_dict = self._as_dict(config)
        self._validate()

    def _as_dict(self, config):
        conf_dict = self.DEFAULTS
        for section in config.sections():
            if section not in conf_dict:
                conf_dict[section] = {}
            for key, val in config.items(section):
                conf_dict[section][key] = val

        return conf_dict

    def _validate(self):
        self._conf_dict['log']['debug'] = utils.str2bool(
            self._conf_dict['log']['debug'])

        self._conf_dict['default']['show_passwords'] = utils.str2bool(
            self._conf_dict['default']['show_passwords'])

        self._conf_dict['ipmi']['session_timeout'] = int(
            self._conf_dict['ipmi']['session_timeout'])

    def __getitem__(self, key):
        return self._conf_dict[key]


def get_config():
    global CONFIG
    if CONFIG is None:
        CONFIG = VirtualBMCConfig()
        CONFIG.initialize()

    return CONFIG
