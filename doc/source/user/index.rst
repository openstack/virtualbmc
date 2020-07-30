
How to use VirtualBMC
=====================

For the VirtualBMC tool to operate you first need to create libvirt
domain(s) for example, via ``virsh``.

The VirtualBMC tool is a client-server system where ``vbmcd`` server
does all the heavy-lifting (speaks IPMI, calls libvirt) while ``vbmc``
client is merely a command-line tool sending commands to the server and
rendering responses to the user.

Both tools can make use of an optional configuration file, which is
looked for in the following locations (in this order):

* ``VIRTUALBMC_CONFIG`` environment variable pointing to a file
* ``$HOME/.vbmc/virtualbmc.conf`` file
* ``/etc/virtualbmc/virtualbmc.conf`` file

If no configuration file has been found, the internal defaults apply.

You should set up your systemd to launch the ``vbmcd`` server on system
start up or you can just run ``vbmcd`` from command line if you do not need
the tool running persistently on the system. Once the server is up and
running, you can use the ``vbmc`` tool to configure your libvirt domains as
if they were physical hardware servers.

The ``vbmc`` client can only communicate with ``vbmcd`` server if both are
running on the same host. However ``vbmcd`` can manage libvirt domains
remotely.

By this moment you should be able to have the ``ipmitool`` managing
VirtualBMC instances over the network.

Configuring virtual servers
---------------------------

Use the ``vbmc`` command-line tool to create, delete, list, start and
stop virtual BMCs for the virtual machines being managed over IPMI.

* In order to see all command options supported by the ``vbmc`` tool
  do::

    $ vbmc --help


  It's also possible to list the options from a specific command. For
  example, in order to know what can be provided as part of the ``add``
  command do::

    $ vbmc add --help


* Adding a new virtual BMC to control libvirt domain called ``node-0``::

    $ vbmc add node-0


* Adding a new virtual BMC to control libvirt domain called ``node-1``
  that will listen for IPMI commands on port ``6230``::

    $ vbmc add node-1 --port 6230


  Alternatively, libvirt can be configured to ssh into a remote machine
  and manage libvirt domain through ssh connection::

    $ vbmc add node-1 --port 6230 \
        --libvirt-uri qemu+ssh://username@192.168.122.1/system

.. note::

   Binding a network port number below 1025 is restricted and only users
   with privilege will be able to start a virtual BMC on those ports.


* Starting the virtual BMC to control libvirt domain ``node-0``::

    $ vbmc start node-0


* Stopping the virtual BMC that controls libvirt domain ``node-0``::

    $ vbmc stop node-0


* Getting the list of virtual BMCs including their libvirt domains and
  IPMI network endpoints they are reachable at::

    $ vbmc list
    +-------------+---------+---------+------+
    | Domain name |  Status | Address | Port |
    +-------------+---------+---------+------+
    |    node-0   | running |    ::   | 623  |
    |    node-1   | running |    ::   | 6230 |
    +-------------+---------+---------+------+

* To view configuration information for a specific virtual BMC::

    $ vbmc show node-0
    +-----------------------+----------------+
    |        Property       |     Value      |
    +-----------------------+----------------+
    |        address        |       ::       |
    |      domain_name      |     node-0     |
    | libvirt_sasl_password |      ***       |
    | libvirt_sasl_username |      None      |
    |      libvirt_uri      | qemu:///system |
    |        password       |      ***       |
    |          port         |      623       |
    |         status        |    running     |
    |        username       |     admin      |
    +-----------------------+----------------+


Server simulation
-----------------

Once the virtual BMC for a specific domain has been created and started
you can then issue IPMI commands against the address and port of that
virtual BMC to control the libvirt domain. For example:

* To power on the virtual machine::

    $ ipmitool -I lanplus -U admin -P password -H 127.0.0.1 -p 6230 power on

* To check its power status::

    $ ipmitool -I lanplus -U admin -P password -H 127.0.0.1 -p 6230 power status

* To set the boot device to disk::

    $ ipmitool -I lanplus -U admin -P password -H 127.0.0.1 -p 6230 chassis bootdev disk

* To get the current boot device::

    $ ipmitool -I lanplus -U admin -P password -H 127.0.0.1 -p 6230 chassis bootparam get 5

Backward compatible behaviour
-----------------------------

In the past the ``vbmc`` tool was the only part of the vBMC system. To help
users keeping their existing server-less workflows, the ``vbmc`` tool
attempts to spawn the ``vbmcd`` piece whenever it figures server is not
running.

.. warning::

   The backward compabible behaviour will be removed in two-cycle time past
   Queens.
