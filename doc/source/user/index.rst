=====
Usage
=====

``vbmc`` is a CLI that lets users create, delete, list, start and stop
virtual BMCs for controlling virtual machines using IPMI commands.


Command options
---------------

In order to see all command options supporter by ``vbmc`` do::

    $ vbmc --help

It's also possible to list the options from a specific command. For
example, in order to know what can be provided as part of the ``add``
command do::

    $ vbmc add --help


Useful examples
---------------

* Adding a new virtual BMC to control a domain called ``node-0``::

    $ vbmc add node-0


* Adding a new virtual BMC to control a domain called ``node-1`` that
  will listen on the port ``6230``::

    $ vbmc add node-0 --port 6230


.. note::
   Binding a network port number below 1025 is restricted and only users
   with privilege will be able to start a virtual BMC on those ports.


* Starting the virtual BMC to control the domain ``node-0``::

    $ vbmc start node-0


* Stopping the virtual BMC that controls the domain ``node-0``::

    $ vbmc stop node-0


* Getting the list of virtual BMCs::

    $ vbmc list
    +-------------+---------+---------+------+
    | Domain name |  Status | Address | Port |
    +-------------+---------+---------+------+
    |    node-0   | running |    ::   | 6230 |
    |    node-1   | running |    ::   | 6231 |
    +-------------+---------+---------+------+


* Showing the information of a specific virtual BMC::

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
    |          port         |      6230      |
    |         status        |    running     |
    |        username       |     admin      |
    +-----------------------+----------------+


Testing
-------

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
