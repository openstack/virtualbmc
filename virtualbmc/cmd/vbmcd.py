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

import argparse
import os
import sys
import tempfile

import virtualbmc
from virtualbmc import config as vbmc_config
from virtualbmc import control
from virtualbmc import log
from virtualbmc import utils


LOG = log.get_logger()

CONF = vbmc_config.get_config()


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        prog='VirtualBMC server',
        description='A virtual BMC server for controlling virtual instances',
    )
    parser.add_argument('--version', action='version',
                        version=virtualbmc.__version__)
    parser.add_argument('--foreground',
                        action='store_true',
                        default=False,
                        help='Do not daemonize')

    args = parser.parse_args(argv)

    pid_file = CONF['default']['pid_file']

    try:
        with open(pid_file) as f:
            pid = int(f.read())

        os.kill(pid, 0)

    except Exception:
        pass

    else:
        LOG.error('server PID #%(pid)d still running', {'pid': pid})
        return 1

    def wrap_with_pidfile(func, pid):
        dir_name = os.path.dirname(pid_file)

        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o700)

        try:
            with tempfile.NamedTemporaryFile(mode='w+t', dir=dir_name,
                                             delete=False) as f:
                f.write(str(pid))
                os.rename(f.name, pid_file)

            func()

        except Exception as e:
            LOG.error('%(error)s', {'error': e})
            return 1

        finally:
            try:
                os.unlink(pid_file)

            except Exception:
                pass

    if args.foreground:
        return wrap_with_pidfile(control.application, os.getpid())

    else:
        with utils.detach_process() as pid:
            if pid > 0:
                return 0

            return wrap_with_pidfile(control.application, pid)


if __name__ == '__main__':
    sys.exit(main())
