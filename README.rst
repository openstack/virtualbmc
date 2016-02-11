Virtual BMC
===========

A virtual BMC for controlling virtual machines with IPMI commands

Usage
-----

#. Create a virtual machine

#. Run the virtual BMC::

      python ./virtualbmc.py --domain-name <virtual machine name>

#. Control it via IPMI::

     # Power the virtual machine on or off
     ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power on|off

     # Check the power status
     ipmitool -I lanplus -U admin -P password -H 127.0.0.1 power status

     # Set the boot device to network, hd or cdrom
     ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootdev pxe|disk|cdrom

     # Get the current boot device
     ipmitool -I lanplus -U admin -P password -H 127.0.0.1 chassis bootparam get 5
