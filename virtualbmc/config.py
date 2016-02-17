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

import utils

__all__ = ['get_config']

CONFIG_FILE = os.path.join(utils.CONFIG_PATH, 'virtualbmc.conf')

CONFIG = None


class VirtualBMCConfig(object):

    DEFAULTS = {'log': {'logfile': None,
                        'debug': 'false'}}

    def __init__(self):
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

    def __getitem__(self, key):
        return self._conf_dict[key]


def get_config():
    global CONFIG
    if CONFIG is None:
        CONFIG = VirtualBMCConfig()

    return CONFIG
