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

import errno
import logging

from virtualbmc import config

__all__ = ['get_logger']

DEFAULT_LOG_FORMAT = ('%(asctime)s.%(msecs)03d %(process)d %(levelname)s '
                      '%(name)s [-] %(message)s')
LOGGER = None


class VirtualBMCLogger(logging.Logger):

    def __init__(self, debug=False, logfile=None):
        logging.Logger.__init__(self, 'VirtualBMC')
        try:
            if logfile is not None:
                self.handler = logging.FileHandler(logfile)
            else:
                self.handler = logging.StreamHandler()

            formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
            self.handler.setFormatter(formatter)
            self.addHandler(self.handler)

            if debug:
                self.setLevel(logging.DEBUG)
            else:
                self.setLevel(logging.INFO)

        except IOError as e:
            if e.errno == errno.EACCES:
                pass


def get_logger():
    global LOGGER
    if LOGGER is None:
        log_conf = config.get_config()['log']
        LOGGER = VirtualBMCLogger(debug=log_conf['debug'],
                                  logfile=log_conf['logfile'])

    return LOGGER
