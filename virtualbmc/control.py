# Copyright 2017 Red Hat, Inc.
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

import json
import signal
import sys

import zmq

from virtualbmc import config as vbmc_config
from virtualbmc import exception
from virtualbmc import log
from virtualbmc.manager import VirtualBMCManager

CONF = vbmc_config.get_config()

LOG = log.get_logger()

TIMER_PERIOD = 3000  # milliseconds


def main_loop(vbmc_manager, handle_command):
    """Server part of the CLI control interface

    Receives JSON messages from ZMQ socket, calls the command handler and
    sends JSON response back to the client.

    Client builds requests out of its command-line options which
    include the command (e.g. `start`, `list` etc) and command-specific
    options.

    Server handles the commands and responds with a JSON document which
    contains at least the `rc` and `msg` attributes, used to indicate the
    outcome of the command, and optionally 2-D table conveyed through the
    `header` and `rows` attributes pointing to lists of cell values.
    """
    server_port = CONF['default']['server_port']

    context = socket = None

    try:
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.setsockopt(zmq.LINGER, 5)
        socket.bind("tcp://127.0.0.1:%s" % server_port)

        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)

        LOG.info('Started vBMC server on port %s', server_port)

        while True:
            socks = dict(poller.poll(timeout=TIMER_PERIOD))
            if socket in socks and socks[socket] == zmq.POLLIN:
                message = socket.recv()
            else:
                vbmc_manager.periodic()
                continue

            try:
                data_in = json.loads(message.decode('utf-8'))

            except ValueError as ex:
                LOG.warning(
                    'Control server request deserialization error: '
                    '%(error)s', {'error': ex}
                )
                continue

            LOG.debug('Command request data: %(request)s',
                      {'request': data_in})

            try:
                data_out = handle_command(vbmc_manager, data_in)

            except exception.VirtualBMCError as ex:
                msg = 'Command failed: %(error)s' % {'error': ex}
                LOG.error(msg)
                data_out = {
                    'rc': 1,
                    'msg': [msg]
                }

            LOG.debug('Command response data: %(response)s',
                      {'response': data_out})

            try:
                message = json.dumps(data_out)

            except ValueError as ex:
                LOG.warning(
                    'Control server response serialization error: '
                    '%(error)s', {'error': ex}
                )
                continue

            socket.send(message.encode('utf-8'))

    finally:
        if socket:
            socket.close()
        if context:
            context.destroy()


def command_dispatcher(vbmc_manager, data_in):
    """Control CLI command dispatcher

    Calls vBMC manager to execute commands, implements uniform
    dictionary-based interface to the caller.
    """
    command = data_in.pop('command')

    LOG.debug('Running "%(cmd)s" command handler', {'cmd': command})

    if command == 'add':

        # Check if the username and password were given for SASL
        sasl_user = data_in['libvirt_sasl_username']
        sasl_pass = data_in['libvirt_sasl_password']
        if any((sasl_user, sasl_pass)):
            if not all((sasl_user, sasl_pass)):
                error = ("A password and username are required to use "
                         "Libvirt's SASL authentication")
                return {'msg': [error], 'rc': 1}

        rc, msg = vbmc_manager.add(**data_in)

        return {
            'rc': rc,
            'msg': [msg] if msg else []
        }

    elif command == 'delete':
        data_out = [vbmc_manager.delete(domain_name)
                    for domain_name in set(data_in['domain_names'])]
        return {
            'rc': max(rc for rc, msg in data_out),
            'msg': [msg for rc, msg in data_out if msg],
        }

    elif command == 'start':
        data_out = [vbmc_manager.start(domain_name)
                    for domain_name in set(data_in['domain_names'])]
        return {
            'rc': max(rc for rc, msg in data_out),
            'msg': [msg for rc, msg in data_out if msg],
        }

    elif command == 'stop':
        data_out = [vbmc_manager.stop(domain_name)
                    for domain_name in set(data_in['domain_names'])]
        return {
            'rc': max(rc for rc, msg in data_out),
            'msg': [msg for rc, msg in data_out if msg],
        }

    elif command == 'list':
        rc, tables = vbmc_manager.list()

        header = ('Domain name', 'Status', 'Address', 'Port')
        keys = ('domain_name', 'status', 'address', 'port')
        return {
            'rc': rc,
            'header': header,
            'rows': [
                [table.get(key, '?') for key in keys] for table in tables
            ]
        }

    elif command == 'show':
        rc, table = vbmc_manager.show(data_in['domain_name'])

        return {
            'rc': rc,
            'header': ('Property', 'Value'),
            'rows': table,
        }

    else:
        return {
            'rc': 1,
            'msg': ['Unknown command'],
        }


def application():
    """vbmcd application entry point

    Initializes, serves and cleans up everything.
    """
    vbmc_manager = VirtualBMCManager()

    vbmc_manager.periodic()

    def kill_children(*args):
        vbmc_manager.periodic(shutdown=True)
        sys.exit(0)

    # SIGTERM does not seem to propagate to multiprocessing
    signal.signal(signal.SIGTERM, kill_children)

    try:
        main_loop(vbmc_manager, command_dispatcher)
    except KeyboardInterrupt:
        LOG.info('Got keyboard interrupt, exiting')
        vbmc_manager.periodic(shutdown=True)
    except Exception as ex:
        LOG.error(
            'Control server error: %(error)s', {'error': ex}
        )
        vbmc_manager.periodic(shutdown=True)
