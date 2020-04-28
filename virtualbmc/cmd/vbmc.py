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

import json
import logging
import sys

from cliff.app import App
from cliff.command import Command
from cliff.commandmanager import CommandManager
from cliff.lister import Lister
import zmq

import virtualbmc
from virtualbmc import config as vbmc_config
from virtualbmc.exception import VirtualBMCError
from virtualbmc import log

CONF = vbmc_config.get_config()

LOG = log.get_logger()


class ZmqClient(object):
    """Client part of the VirtualBMC system.

    The command-line client tool communicates with the server part
    of the VirtualBMC system by exchanging JSON-encoded messages.

    Client builds requests out of its command-line options which
    include the command (e.g. `start`, `list` etc) and command-specific
    options.

    Server response is a JSON document which contains at least the
    `rc` and `msg` attributes, used to indicate the outcome of the
    command, and optionally 2-D table conveyed through the `header`
    and `rows` attributes pointing to lists of cell values.
    """

    SERVER_TIMEOUT = CONF['default']['server_response_timeout']

    @staticmethod
    def to_dict(obj):
        return {attr: getattr(obj, attr)
                for attr in dir(obj) if not attr.startswith('_')}

    def communicate(self, command, args, no_daemon=False):

        data_out = self.to_dict(args)

        data_out.update(command=command)

        data_out = json.dumps(data_out)

        server_port = CONF['default']['server_port']

        context = socket = None

        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.LINGER, 5)
            socket.connect("tcp://127.0.0.1:%s" % server_port)

            poller = zmq.Poller()
            poller.register(socket, zmq.POLLIN)

            try:
                socket.send(data_out.encode('utf-8'))

                socks = dict(poller.poll(timeout=self.SERVER_TIMEOUT))
                if socket in socks and socks[socket] == zmq.POLLIN:
                    data_in = socket.recv()

                else:
                    raise zmq.ZMQError(
                        zmq.RCVTIMEO, msg='Server response timed out')

            except zmq.ZMQError as ex:
                msg = ('Failed to connect to the vbmcd server on port '
                       '%(port)s, error: %(error)s' % {'port': server_port,
                                                       'error': ex})
                LOG.error(msg)
                raise VirtualBMCError(msg)

        finally:
            if socket:
                socket.close()
                context.destroy()

        try:
            data_in = json.loads(data_in.decode('utf-8'))

        except ValueError as ex:
            msg = 'Server response parsing error %(error)s' % {'error': ex}
            LOG.error(msg)
            raise VirtualBMCError(msg)

        rc = data_in.pop('rc', None)
        if rc:
            msg = '(%(rc)s): %(msg)s' % {
                'rc': rc,
                'msg': '\n'.join(data_in.get('msg', ()))
            }
            LOG.error(msg)
            raise VirtualBMCError(msg)

        return data_in


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
                raise VirtualBMCError(msg)

        self.app.zmq.communicate(
            'add', args, no_daemon=self.app.options.no_daemon
        )


class DeleteCommand(Command):
    """Delete a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(DeleteCommand, self).get_parser(prog_name)

        parser.add_argument('domain_names', nargs='+',
                            help='A list of virtual machine names')

        return parser

    def take_action(self, args):
        self.app.zmq.communicate('delete', args, self.app.options.no_daemon)


class StartCommand(Command):
    """Start a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(StartCommand, self).get_parser(prog_name)

        parser.add_argument('domain_names', nargs='+',
                            help='A list of virtual machine names')

        return parser

    def take_action(self, args):
        self.app.zmq.communicate(
            'start', args, no_daemon=self.app.options.no_daemon
        )


class StopCommand(Command):
    """Stop a virtual BMC for a virtual machine instance"""

    def get_parser(self, prog_name):
        parser = super(StopCommand, self).get_parser(prog_name)

        parser.add_argument('domain_names', nargs='+',
                            help='A list of virtual machine names')

        return parser

    def take_action(self, args):
        self.app.zmq.communicate(
            'stop', args, no_daemon=self.app.options.no_daemon
        )


class ListCommand(Lister):
    """List all virtual BMC instances"""

    def take_action(self, args):
        rsp = self.app.zmq.communicate(
            'list', args, no_daemon=self.app.options.no_daemon
        )
        return rsp['header'], sorted(rsp['rows'])


class ShowCommand(Lister):
    """Show virtual BMC properties"""

    def get_parser(self, prog_name):
        parser = super(ShowCommand, self).get_parser(prog_name)

        parser.add_argument('domain_name',
                            help='The name of the virtual machine')

        return parser

    def take_action(self, args):
        rsp = self.app.zmq.communicate(
            'show', args, no_daemon=self.app.options.no_daemon
        )
        return rsp['header'], sorted(rsp['rows'])


class VirtualBMCApp(App):

    def __init__(self):
        super(VirtualBMCApp, self).__init__(
            description='Virtual Baseboard Management Controller (BMC) backed '
                        'by virtual machines',
            version=virtualbmc.__version__,
            command_manager=CommandManager('virtualbmc'),
            deferred_help=True,
        )

    def build_option_parser(self, description, version, argparse_kwargs=None):
        parser = super(VirtualBMCApp, self).build_option_parser(
            description, version, argparse_kwargs
        )

        parser.add_argument('--no-daemon',
                            action='store_true',
                            help='Do not start vbmcd automatically')

        return parser

    def initialize_app(self, argv):
        self.zmq = ZmqClient()

    def clean_up(self, cmd, result, err):
        self.LOG.debug('clean_up %(name)s', {'name': cmd.__class__.__name__})
        if err:
            self.LOG.debug('got an error: %(error)s', {'error': err})


def main(argv=sys.argv[1:]):
    vbmc_app = VirtualBMCApp()
    return vbmc_app.run(argv)


if __name__ == '__main__':
    sys.exit(main())
