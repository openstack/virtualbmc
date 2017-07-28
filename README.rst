==========
VirtualBMC
==========

A virtual BMC for controlling virtual machines using IPMI commands.

Installation
------------

.. code-block:: bash

  pip install virtualbmc

Supported IPMI commands
-----------------------

.. code-block:: bash

  # Power the virtual machine on, off, graceful off, NMI and reset
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power on|off|soft|diag|reset

  # Check the power status
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power status

  # Set the boot device to network, hd or cdrom
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootdev pxe|disk|cdrom

  # Get the current boot device
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootparam get 5

  # Get the current boot device
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootparam get 5

Team and repository tags
------------------------

.. image:: https://governance.openstack.org/tc/badges/virtualbmc.svg
    :target: https://governance.openstack.org/tc/reference/tags/index.html

.. Change things from this point on

