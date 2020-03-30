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

import configparser
import errno
import multiprocessing
import os
import shutil
import signal

from virtualbmc import config as vbmc_config
from virtualbmc import exception
from virtualbmc import log
from virtualbmc import utils
from virtualbmc.vbmc import VirtualBMC

LOG = log.get_logger()

# BMC status
RUNNING = 'running'
DOWN = 'down'
ERROR = 'error'

DEFAULT_SECTION = 'VirtualBMC'

CONF = vbmc_config.get_config()


class VirtualBMCManager(object):

    VBMC_OPTIONS = ['username', 'password', 'address', 'port',
                    'domain_name', 'libvirt_uri', 'libvirt_sasl_username',
                    'libvirt_sasl_password', 'active']

    def __init__(self):
        super(VirtualBMCManager, self).__init__()
        self.config_dir = CONF['default']['config_dir']
        self._running_domains = {}

    def _parse_config(self, domain_name):
        config_path = os.path.join(self.config_dir, domain_name, 'config')
        if not os.path.exists(config_path):
            raise exception.DomainNotFound(domain=domain_name)

        try:
            config = configparser.ConfigParser()
            config.read(config_path)

            bmc = {}
            for item in self.VBMC_OPTIONS:
                try:
                    value = config.get(DEFAULT_SECTION, item)
                except configparser.NoOptionError:
                    value = None

                bmc[item] = value

            # Port needs to be int
            bmc['port'] = config.getint(DEFAULT_SECTION, 'port')

            return bmc

        except OSError:
            raise exception.DomainNotFound(domain=domain_name)

    def _store_config(self, **options):
        config = configparser.ConfigParser()
        config.add_section(DEFAULT_SECTION)

        for option, value in options.items():
            if value is not None:
                config.set(DEFAULT_SECTION, option, str(value))

        config_path = os.path.join(
            self.config_dir, options['domain_name'], 'config'
        )

        with open(config_path, 'w') as f:
            config.write(f)

    def _vbmc_enabled(self, domain_name, lets_enable=None, config=None):
        if not config:
            config = self._parse_config(domain_name)

        try:
            currently_enabled = utils.str2bool(config['active'])

        except Exception:
            currently_enabled = False

        if (lets_enable is not None
                and lets_enable != currently_enabled):
            config.update(active=lets_enable)
            self._store_config(**config)
            currently_enabled = lets_enable

        return currently_enabled

    def _sync_vbmc_states(self, shutdown=False):
        """Starts/stops vBMC instances

        Walks over vBMC instances configuration, starts
        enabled but dead instances, kills non-configured
        but alive ones.
        """

        def vbmc_runner(bmc_config):
            # The manager process installs a signal handler for SIGTERM to
            # propagate it to children. Return to the default handler.
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

            show_passwords = CONF['default']['show_passwords']

            if show_passwords:
                show_options = bmc_config
            else:
                show_options = utils.mask_dict_password(bmc_config)

            try:
                vbmc = VirtualBMC(**bmc_config)

            except Exception as ex:
                LOG.exception(
                    'Error running vBMC with configuration '
                    '%(opts)s: %(error)s', {'opts': show_options,
                                            'error': ex}
                )
                return

            try:
                vbmc.listen(timeout=CONF['ipmi']['session_timeout'])

            except Exception as ex:
                LOG.exception(
                    'Shutdown vBMC for domain %(domain)s, cause '
                    '%(error)s', {'domain': show_options['domain_name'],
                                  'error': ex}
                )
                return

        for domain_name in os.listdir(self.config_dir):
            if not os.path.isdir(
                    os.path.join(self.config_dir, domain_name)
            ):
                continue

            try:
                bmc_config = self._parse_config(domain_name)

            except exception.DomainNotFound:
                continue

            if shutdown:
                lets_enable = False
            else:
                lets_enable = self._vbmc_enabled(
                    domain_name, config=bmc_config
                )

            instance = self._running_domains.get(domain_name)

            if lets_enable:

                if not instance or not instance.is_alive():

                    instance = multiprocessing.Process(
                        name='vbmcd-managing-domain-%s' % domain_name,
                        target=vbmc_runner,
                        args=(bmc_config,)
                    )

                    instance.daemon = True
                    instance.start()

                    self._running_domains[domain_name] = instance

                    LOG.info(
                        'Started vBMC instance for domain '
                        '%(domain)s', {'domain': domain_name}
                    )

                if not instance.is_alive():
                    LOG.debug(
                        'Found dead vBMC instance for domain %(domain)s '
                        '(rc %(rc)s)', {'domain': domain_name,
                                        'rc': instance.exitcode}
                    )

            else:
                if instance:
                    if instance.is_alive():
                        instance.terminate()
                        LOG.info(
                            'Terminated vBMC instance for domain '
                            '%(domain)s', {'domain': domain_name}
                        )

                    self._running_domains.pop(domain_name, None)

    def _show(self, domain_name):
        bmc_config = self._parse_config(domain_name)

        show_passwords = CONF['default']['show_passwords']

        if show_passwords:
            show_options = bmc_config
        else:
            show_options = utils.mask_dict_password(bmc_config)

        instance = self._running_domains.get(domain_name)

        if instance and instance.is_alive():
            show_options['status'] = RUNNING
        elif instance and not instance.is_alive():
            show_options['status'] = ERROR
        else:
            show_options['status'] = DOWN

        return show_options

    def periodic(self, shutdown=False):
        self._sync_vbmc_states(shutdown)

    def add(self, username, password, port, address, domain_name,
            libvirt_uri, libvirt_sasl_username, libvirt_sasl_password,
            **kwargs):

        # check libvirt's connection and if domain exist prior to adding it
        utils.check_libvirt_connection_and_domain(
            libvirt_uri, domain_name,
            sasl_username=libvirt_sasl_username,
            sasl_password=libvirt_sasl_password)

        domain_path = os.path.join(self.config_dir, domain_name)

        try:
            os.makedirs(domain_path)
        except OSError as ex:
            if ex.errno == errno.EEXIST:
                return 1, str(ex)

            msg = ('Failed to create domain %(domain)s. '
                   'Error: %(error)s' % {'domain': domain_name, 'error': ex})
            LOG.error(msg)
            return 1, msg

        try:
            self._store_config(domain_name=domain_name,
                               username=username,
                               password=password,
                               port=str(port),
                               address=address,
                               libvirt_uri=libvirt_uri,
                               libvirt_sasl_username=libvirt_sasl_username,
                               libvirt_sasl_password=libvirt_sasl_password,
                               active=False)

        except Exception as ex:
            self.delete(domain_name)
            return 1, str(ex)

        return 0, ''

    def delete(self, domain_name):
        domain_path = os.path.join(self.config_dir, domain_name)
        if not os.path.exists(domain_path):
            raise exception.DomainNotFound(domain=domain_name)

        try:
            self.stop(domain_name)
        except exception.VirtualBMCError:
            pass

        shutil.rmtree(domain_path)

        return 0, ''

    def start(self, domain_name):
        try:
            bmc_config = self._parse_config(domain_name)

        except Exception as ex:
            return 1, str(ex)

        if domain_name in self._running_domains:

            self._sync_vbmc_states()

            if domain_name in self._running_domains:
                LOG.warning(
                    'BMC instance %(domain)s already running, ignoring '
                    '"start" command' % {'domain': domain_name})
                return 0, ''

        try:
            self._vbmc_enabled(domain_name,
                               config=bmc_config,
                               lets_enable=True)

        except Exception as e:
            LOG.exception('Failed to start domain %s', domain_name)
            return 1, ('Failed to start domain %(domain)s. Error: '
                       '%(error)s' % {'domain': domain_name, 'error': e})

        self._sync_vbmc_states()

        return 0, ''

    def stop(self, domain_name):
        try:
            self._vbmc_enabled(domain_name, lets_enable=False)

        except Exception as ex:
            LOG.exception('Failed to stop domain %s', domain_name)
            return 1, str(ex)

        self._sync_vbmc_states()

        return 0, ''

    def list(self):
        rc = 0
        tables = []
        try:
            for domain in os.listdir(self.config_dir):
                if os.path.isdir(os.path.join(self.config_dir, domain)):
                    tables.append(self._show(domain))

        except OSError as e:
            if e.errno == errno.EEXIST:
                rc = 1

        return rc, tables

    def show(self, domain_name):
        return 0, list(self._show(domain_name).items())
