==========
VirtualBMC
==========

Team and repository tags
------------------------

.. image:: https://governance.openstack.org/tc/badges/virtualbmc.svg
    :target: https://governance.openstack.org/tc/reference/tags/index.html

Overview
--------

A virtual BMC for controlling virtual machines using IPMI commands.

This software is intended for CI and development use only. Please do not run
VirtualBMC in a production environment for any reason.

Installation
~~~~~~~~~~~~

.. code-block:: bash

  pip install virtualbmc


Supported IPMI commands
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

  # Power the virtual machine on, off, graceful off, NMI and reset
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power on|off|soft|diag|reset

  # Check the power status
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power status

  # Set the boot device to network, hd or cdrom
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootdev pxe|disk|cdrom

  # Get the current boot device
  ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootparam get 5

Project resources
~~~~~~~~~~~~~~~~~

* Documentation: https://docs.openstack.org/virtualbmc/latest
* Source: https://opendev.org/openstack/virtualbmc
* Bugs: https://storyboard.openstack.org/#!/project/openstack/virtualbmc
* Release Notes: https://docs.openstack.org/releasenotes/virtualbmc/

Project status, bugs, and requests for feature enhancements (RFEs) are tracked
in StoryBoard:
https://storyboard.openstack.org/#!/project/openstack/virtualbmc

For information on how to contribute to VirtualBMC, see
https://docs.openstack.org/virtualbmc/latest/contributor

