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

import logging
import sys

from cliff.app import App
from cliff.command import Command
from cliff.commandmanager import CommandManager
from cliff.lister import Lister

import virtualbmc
from virtualbmc import exception
from virtualbmc.manager import VirtualBMCManager


class AddCommand(Command):
    """Create a new BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(AddCommand, self).get_parser(prog_name)

        parser.add_argument('domain_name',
                            help='The name of the virtual machine')
        parser.add_argument('--username',
                            dest='username',
                            default='admin',
                            help='The BMC username; defaults to "admin"')
        parser.add_argument('--password',
                            dest='password',
                            default='password',
                            help='The BMC password; defaults to "password"')
        parser.add_argument('--port',
                            dest='port',
                            type=int,
                            default=623,
                            help='Port to listen on; defaults to 623')
        parser.add_argument('--address',
                            dest='address',
                            default='::',
                            help=('The address to bind to (IPv4 and IPv6 '
                                  'are supported); defaults to ::'))
        parser.add_argument('--libvirt-uri',
                            dest='libvirt_uri',
                            default="qemu:///system",
                            help=('The libvirt URI; defaults to '
                                  '"qemu:///system"'))
        parser.add_argument('--libvirt-sasl-username',
                            dest='libvirt_sasl_username',
                            default=None,
                            help=('The libvirt SASL username; defaults to '
                                  'None'))
        parser.add_argument('--libvirt-sasl-password',
                            dest='libvirt_sasl_password',
                            default=None,
                            help=('The libvirt SASL password; defaults to '
                                  'None'))
        return parser

    def take_action(self, args):

        log = logging.getLogger(__name__)

        # Check if the username and password were given for SASL
        sasl_user = args.libvirt_sasl_username
        sasl_pass = args.libvirt_sasl_password
        if any((sasl_user, sasl_pass)):
            if not all((sasl_user, sasl_pass)):
                msg = ("A password and username are required to use "
                       "Libvirt's SASL authentication")
                log.error(msg)
                raise exception.VirtualBMCError(msg)

        self.app.manager.add(username=args.username, password=args.password,
                             port=args.port, address=args.address,
                             domain_name=args.domain_name,
                             libvirt_uri=args.libvirt_uri,
                             libvirt_sasl_username=sasl_user,
                             libvirt_sasl_password=sasl_pass)


class DeleteCommand(Command):
    """Delete a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(DeleteCommand, self).get_parser(prog_name)

        parser.add_argument('domain_names', nargs='+',
                            help='A list of virtual machine names')

        return parser

    def take_action(self, args):
        for domain in args.domain_names:
            self.app.manager.delete(domain)


class StartCommand(Command):
    """Start a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(StartCommand, self).get_parser(prog_name)

        parser.add_argument('domain_name',
                            help='The name of the virtual machine')

        return parser

    def take_action(self, args):
        self.app.manager.start(args.domain_name)


class StopCommand(Command):
    """Stop a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(StopCommand, self).get_parser(prog_name)

        parser.add_argument('domain_names', nargs='+',
                            help='A list of virtual machine names')

        return parser

    def take_action(self, args):
        for domain_name in args.domain_names:
            self.app.manager.stop(domain_name)


class ListCommand(Lister):
    """List all virtual BMC instances"""

    def take_action(self, args):
        header = ('Domain name', 'Status', 'Address', 'Port')
        rows = []

        for bmc in self.app.manager.list():
            rows.append(
                ([bmc['domain_name'], bmc['status'],
                  bmc['address'], bmc['port']])
            )

        return header, sorted(rows)


class ShowCommand(Lister):
    """Show virtual BMC properties"""

    def get_parser(self, prog_name):
        parser = super(ShowCommand, self).get_parser(prog_name)

        parser.add_argument('domain_name',
                            help='The name of the virtual machine')

        return parser

    def take_action(self, args):
        header = ('Property', 'Value')
        rows = []

        bmc = self.app.manager.show(args.domain_name)

        for key, val in bmc.items():
            rows.append((key, val))

        return header, sorted(rows)


class VirtualBMCApp(App):

    def __init__(self):
        super(VirtualBMCApp, self).__init__(
            description='Virtual Baseboard Management Controller (BMC) backed '
                        'by virtual machines',
            version=virtualbmc.__version__,
            command_manager=CommandManager('virtualbmc'),
            deferred_help=True,
        )

    def initialize_app(self, argv):
        self.manager = VirtualBMCManager()

    def clean_up(self, cmd, result, err):
        self.LOG.debug('clean_up %s', cmd.__class__.__name__)
        if err:
            self.LOG.debug('got an error: %s', err)


def main(argv=sys.argv[1:]):
    vbmc_app = VirtualBMCApp()
    return vbmc_app.run(argv)


if __name__ == '__main__':
    sys.exit(main())
