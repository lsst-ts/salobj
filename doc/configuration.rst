.. py:currentmodule:: lsst.ts.salobj

.. _lsst.ts.salobj-configuration:

#####################
Configuring ts_salobj
#####################

.. _lsst.ts.salobj-configuration_environment_variables:

Environment Variables
---------------------

Environment variables used by ts_salobj for configuration.
If setting these via `os.environ` please be sure to set these to string values, even if they are parsed as integers or floats.

Used by `Vortex OpenSplice`_, and thus indirectly by `Domain`:

* ``ADLINK_LICENSE`` (optional) points to directory containing your `Vortex OpenSplice`_ license.
  Required if using the licensed version of `Vortex OpenSplice`_.
  Example: ``/opt/ADLINK/Vortex_v2/Device/VortexOpenSplice/6.10.3/HDE/x86_64.linux/etc``
* ``OSPL_HOME`` (required) directory of the `Vortex OpenSplice`_ software.
  This directory should contain subdirectories ``bin``, ``include``, ``lib``, etc.
  Example: ``/opt/OpenSpliceDDS/V6.9.0/HDE/x86_64.linux``. 
* ``OSPL_MASTER_PRIORITY`` (optional) is used to set the Master Priority in ts_sal 4.2 and later.
  Nodes with higher Master Priority are more eager to become master (the primary source of late joiner data).
  Ties are broken by systemId, a random number handed out when a node is created.
  Every time a new node takes over as master, the entire system is must be "aligned", which is expensive,
  so it is best to assign the highest Master Priority to one of nodes that will be created early.
  Valid values are 0-255.
  0 is used for SAL Scripts, because they should never be master.
  256 means "use the legacy method for choosing the master"; do not use it.
  A default value is used if this environment variable is not specified,
  and that default is guaranteed to be >0 and <255.
  Unlike the others in this section, ``OSPL_MASTER_PRIORITY`` is specific to Vera Rubin Observatory.
  If supported (ts_sal 4.2 and later), it will be part of the OpenSplice configuration file pointed to ``OSPL_URI``.
  Constant ``lsst.ts.salobj.MASTER_PRIORITY_ENV_VAR`` is available to make this easier to set from Python.
* ``OSPL_URI`` (required) points to the main DDS configuration file.
  Example: ``file:///home/saluser/tsrepos/ts_opensplice/OpenSpliceDDS/v6.9/HDE/x86_64.linux/etc/config/ospl.xml``

Used by `SalInfo`:

* ``LSST_DDS_PARTITION_PREFIX`` (required): a prefix for DDS partition names.
  This is read by `SalInfo` so that different instances of `SalInfo` (thus different `Remote`\ s and `Controller`\ s) can communicate with different DDS partitions, even though all share the same `Domain`.
  See `SalInfo` for DDS partition name details.
* ``LSST_DDS_DOMAIN`` (deprecated): a deprecated alias for ``LSST_DDS_PARTITION_PREFIX`` that is used if ``LSST_DDS_PARTITION_PREFIX`` is not defined.
* ``LSST_DDS_HISTORYSYNC`` (optional): time limit (sec) for waiting for historical (late-joiner) data.
  If, and only if, you are running DDS without a durability service then set this negative to avoid waiting for historical data.

Used by `AsyncS3Bucket`:

* ``S3_ENDPOINT_URL``: The endpoint URL for the S3 server, e.g. ``http://foo.bar:9000``.
  You must specify a value in order to use an S3 service that is not part of Amazon Web Services (AWS).
  Eventually we hope that ``endpoint_url`` can be defined in ``~/.aws/config``.
  Once that is supported you can leave this environment variable unset, and we can deprecate it.

.. _lsst.ts.salobj-configuration_other:

Other Configuration
-------------------

In addition to the environment variables described above, you will need the `ts_idl`_ package and, if you wish to build topic schemas, the `ts_sal`_ package.

The `Vortex OpenSplice`_ DDS quality of service is specified by the file ``qos/DDS_DefaultQoS_All.xml`` in `ts_idl`_.

DDS topic schemas are defined by ``OMG IDL`` files, which are contained in the ``idl`` directory of the `ts_idl`_ package.
You may generate new IDL files using the ``make_idl_files.py`` command-line script in the `ts_sal`_ package.

.. _Vortex OpenSplice: https://istkb.adlinktech.com/article/vortex-opensplice-documentation/
.. _ts_sal: https://github.com/lsst-ts/ts_sal
.. _ts_idl: https://github.com/lsst-ts/ts_idl
