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


def get_domain(**kwargs):
    domain = {'domain_name': kwargs.get('domain_name', 'SpongeBob'),
              'address': kwargs.get('address', '::'),
              'port': kwargs.get('port', 123),
              'username': kwargs.get('username', 'admin'),
              'password': kwargs.get('password', 'pass'),
              'libvirt_uri': kwargs.get('libvirt_uri', 'foo://bar'),
              'libvirt_sasl_username': kwargs.get('libvirt_sasl_username'),
              'libvirt_sasl_password': kwargs.get('libvirt_sasl_password')}

    status = kwargs.get('status')
    if status is not None:
        domain['status'] = status

    return domain
