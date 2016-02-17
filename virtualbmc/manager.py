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
import os
import sys
import shutil
import signal

import daemon
from six.moves import configparser

import exception
import log
import virtualbmc

LOG = log.get_logger()

# BMC status
RUNNING = 'running'
DOWN = 'down'

DEFAULT_SECTION = 'VirtualBMC'
CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.vbmc')


def is_pid_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class VirtualBMCManager(object):

    def _parse_config(self, domain_name):
        config_path = os.path.join(CONFIG_PATH, domain_name, 'config')
        if not os.path.exists(config_path):
            raise exception.DomainNotFound(domain=domain_name)

        config = configparser.ConfigParser()
        config.read(config_path)

        bmc = {}
        for item in ('username', 'password', 'address',
                     'domain_name', 'libvirt_uri'):
            bmc[item] = config.get(DEFAULT_SECTION, item)

        # Port needs to be int
        bmc['port'] = int(config.get(DEFAULT_SECTION, 'port'))

        return bmc

    def _show(self, domain_name):
        running = False
        try:
            pidfile_path = os.path.join(CONFIG_PATH, domain_name, 'pid')
            with open(pidfile_path, 'r') as f:
                pid = int(f.read())

            running = is_pid_running(pid)
        except IOError:
            pass

        bmc_config = self._parse_config(domain_name)
        bmc_config['status'] = RUNNING if running else DOWN
        return bmc_config

    def add(self, username, password, port, address,
            domain_name, libvirt_uri):
        virtualbmc.check_libvirt_connection_and_domain(
            libvirt_uri, domain_name)

        domain_path = os.path.join(CONFIG_PATH, domain_name)
        try:
            os.makedirs(domain_path)
        except OSError as e:
            if e.errno == errno.EEXIST:
                sys.exit('Domain %s already exist' % domain_name)

        config_path = os.path.join(domain_path, 'config')
        with open(config_path, 'w') as f:
            config = configparser.ConfigParser()
            config.add_section(DEFAULT_SECTION)
            config.set(DEFAULT_SECTION, 'username', username)
            config.set(DEFAULT_SECTION, 'password', password)
            config.set(DEFAULT_SECTION, 'port', port)
            config.set(DEFAULT_SECTION, 'address', address)
            config.set(DEFAULT_SECTION, 'domain_name', domain_name)
            config.set(DEFAULT_SECTION, 'libvirt_uri', libvirt_uri)
            config.write(f)

    def delete(self, domain_name):
        domain_path = os.path.join(CONFIG_PATH, domain_name)
        if not os.path.exists(domain_path):
            raise exception.DomainNotFound(domain=domain_name)

        try:
            self.stop(domain_name)
        except exception.VirtualBMCError:
            pass

        shutil.rmtree(domain_path)

    def start(self, domain_name):
        domain_path = os.path.join(CONFIG_PATH, domain_name)
        if not os.path.exists(domain_path):
            raise exception.DomainNotFound(domain=domain_name)

        bmc_config = self._parse_config(domain_name)

        virtualbmc.check_libvirt_connection_and_domain(
            bmc_config['libvirt_uri'], domain_name)

        LOG.debug('Starting a Virtual BMC for domain %(domain)s with the '
                  'following configuration options: %(config)s',
                  {'domain': domain_name,
                   'config': ' '.join(['%s="%s"' % (k, bmc_config[k])
                                       for k in bmc_config])})

        with daemon.DaemonContext(stderr=sys.stderr,
                                  files_preserve=[LOG.handler.stream, ]):
            # FIXME(lucasagomes): pyghmi start the sockets when the
            # class is instantiated, therefore we need to create the object
            # within the daemon context

            try:
                vbmc = virtualbmc.VirtualBMC(**bmc_config)
            except Exception as e:
                msg = ('Error starting a Virtual BMC for domain %(domain)s. '
                       'Error: %(error)s' % {'domain': domain_name,
                                             'error': e})
                LOG.error(msg)
                raise exception.VirtualBMCError(msg)

            # Save the PID number
            pidfile_path = os.path.join(domain_path, 'pid')
            with open(pidfile_path, 'w') as f:
                f.write(str(os.getpid()))

            LOG.info('Virtual BMC for domain %s started', domain_name)
            vbmc.listen()

    def stop(sel, domain_name):
        LOG.debug('Stopping Virtual BMC for domain %s', domain_name)
        domain_path = os.path.join(CONFIG_PATH, domain_name)
        if not os.path.exists(domain_path):
            raise exception.DomainNotFound(domain=domain_name)

        pidfile_path = os.path.join(domain_path, 'pid')
        pid = None
        try:
            with open(pidfile_path, 'r') as f:
                pid = int(f.read())
        except IOError:
            raise exception.VirtualBMCError(
                'Error stopping the domain %s: PID file not '
                'found' % domain_name)
        else:
            os.remove(pidfile_path)

        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def list(self):
        bmcs = []
        try:
            for domain in os.listdir(CONFIG_PATH):
                bmcs.append(self._show(domain))
        except OSError as e:
            if e.errno == errno.EEXIST:
                return bmcs

        return bmcs

    def show(self, domain_name):
        return self._show(domain_name)
