Serial-over-LAN
===============

VirtualBMC bridges IPMI SOL to the VM's default libvirt console using
``virDomain.openConsole``. This implementation targets ``ipmitool`` and
Ironic's ``ipmitool-socat`` console interface. SOL uses the same address,
UDP port, username, and password as the virtual BMC's power commands.

Prerequisites
-------------

* A libvirt console supported by ``openConsole``, normally a PTY serial
  console. If ``virsh console DOMAIN`` works, this is a suitable starting
  point. Disconnect virsh before activating SOL: VirtualBMC does not force
  another console client off the port.
* Guest serial output/input configured appropriately, for example
  ``console=ttyS0,115200`` and a serial getty for x86 Linux guests. Firmware
  serial redirection is needed to see firmware output.
* A read-write libvirt connection with console access. The BMC's existing
  libvirt URI and SASL credentials are used for the console connection.

Connecting
----------

For a BMC listening on UDP port 6230::

    ipmitool -I lanplus -C 3 -H 192.168.111.1 -p 6230 -U admin -a sol activate

``-a`` prompts for the BMC password. Press Enter if the guest is idle.
Exit with Enter followed by ``~.``. To release a stale SOL session from
another terminal::

    ipmitool -I lanplus -C 3 -H 192.168.111.1 -p 6230 -U admin -a sol deactivate

An external deactivation releases the console immediately. Some ipmitool
versions ignore the unsolicited SOL-inactive notification; exit the old
client locally if it remains open.

Set Ironic's ``driver_info/ipmi_cipher_suite`` to ``3`` when
using this pyghmi server, and select ``console_interface=ipmitool-socat``.
Ironic must also enable that console interface in its configuration. Its
TCP console listener port is separate from the virtual BMC's UDP port.

Scope and limitations
---------------------

* One client, SOL payload instance 1, and the default libvirt console per VM.
  Additional clients are rejected until the owner disconnects or is
  deactivated. Console selection and multiple readers are not implemented.
* Activation while the VM is off is supported. The stream is attached when
  the VM starts and reattached after EOF or a libvirt disconnection, with a
  one-second retry interval. The earliest boot output can be missed during
  this interval; there is no history buffer or log replay.
* Input typed while the console stream is absent is discarded. Input queued
  for an old stream is discarded on disconnection. Partial writes and
  nonblocking I/O are handled; a 4 KiB input queue bounds memory usage and
  an overflow closes SOL. Output is read one acknowledged packet at a time.
* Client sessions expire after 60 seconds without client traffic. Normal
  ipmitool Get Device ID keepalives keep an idle session alive. Lost output
  acknowledgements also cause the console to be released.
* ``sol info``, ``sol set``, per-user payload configuration, and serial BREAK
  are not implemented. The supported client is ``ipmitool`` with its default
  keepalive behavior.
