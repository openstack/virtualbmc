.. virtualbmc documentation master file, created by
   sphinx-quickstart on Tue Jul  9 22:26:36 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to VirtualBMC's documentation!
======================================

The VirtualBMC tool simulates a
`Baseboard Management Controller <https://en.wikipedia.org/wiki/Intelligent_Platform_Management_Interface#Baseboard_management_controller>`_
(BMC) by exposing
`IPMI <https://en.wikipedia.org/wiki/Intelligent_Platform_Management_Interface>`_
responder to the network and talking to
`libvirt <https://en.wikipedia.org/wiki/Libvirt>`_
at the host vBMC is running at to manipulate virtual machines which pretend
to be bare metal servers.

Contents:

.. toctree::
   :maxdepth: 1

   install/index
   user/index
   contributor/index
