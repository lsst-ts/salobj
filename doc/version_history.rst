.. py:currentmodule:: lsst.ts.salobj

.. _lsst.ts.salobj.version_history:

###############
Version History
###############

v6.0.0
======

Backward Incompatible Changes:

* Telemetry topics now have volatile durability.
  All SAL components on your system must use ts_salobj 6 and ts_sal 5 or newer.
* Topics use a new DDS partition naming scheme that is incompatible with ts_sal 4 and ts_salobj 5.
* Requires ts_xml 6 and IDL files built with ts_sal 5 or later, for authorization support.
* Removed deprecated ``main`` method from `BaseCsc` and `BaseScript`.
  Call `BaseCsc.amain` or `BaseScript.amain` instead, e.g. ``asyncio.run(MyCSC(index=...))`` or ``asyncio.run(MyScript.amain())``.
* Removed deprecated ``initial_simulation_mode`` argument from `BaseCsc` and `ConfigurableCsc`.
  Use ``simulation_mode`` instead.
* Removed deprecated support for calling `BaseCsc.fault` without an error code or report; both must now be specified.
* Removed deprecated support for setting ``BaseCsc.summary_state`` directly.
  To transition your CSC to a FAULT state call the `BaseCsc.fault` method.
  Unit tests may call the `set_summary_state` function or issue the usual state transition commands.
* Commands are no longer acknowledged with ``CMD_INPROGRESS`` if the do_xxx callback function is asynchronous.
  This was needlessly chatty.
  Instead users are expected to issue such an ack manually (e.g. by calling `topics.ControllerCommand.ack_in_progress`)
  when beginning to execute a command that will take significant time before it is reported as ``CMD_COMPLETE``.
* Removed the deprecated `SalInfo.idl_loc` property; use ``SalInfo.metadata.idl_path`` instead.
* The `force_output` argument to `topics.ControllerEvent.set_put` is now keyword-only.
* Removed the deprecated `max_history` argument from `topics.ControllerCommand`\ 's constructor.
  Commands are volatile, so historical data is not available.
* Removed ``bin/purge_topics.py`` command-line script, because it is no longer needed.

Deprecations:

* Simplified simulation mode support in CSCs.
  This is described in :ref:`simulation mode<lsst.ts.salobj-simulation_mode>` and results in the following deprecations:

  * CSCs should now set class variable ``valid_simulation_modes``, even if they do not support simulation.
    Failure to do so will result in a deprecation warning, but supports the old way of doing things.
  * Deprecated `BaseCsc.implement_simulation_mode`.
    Start your simulator in whichever other method seems most appropriate.
  * Deprecated the need to override `BaseCsc.add_arguments` and `BaseCsc.add_kwargs_from_args` to add the ``--simulate`` command-line argument.
    This argument is added automatically if ``valid_simulation_modes`` has more than one entry.
* Renamed environment variable ``LSST_DDS_DOMAIN`` to ``LSST_DDS_PARTITION_PREFIX``.
  The old environment variable is used, with a deprecation warning, if the new one is not defined.
* Renamed `SalInfo.makeAckCmd` to `SalInfo.make_ackcmd`.
  The old method is still available, but issues a deprecation warning.
* Renamed `ControllerCommand.ackInProgress` to `ControllerCommand.ack_in_progress` and added a required `timeout` argument.
   The old method is still available, but issues a deprecation warning.
* `Remote`: the ``tel_max_history`` constructor argument is deprecated and should not be specified.
  If specified it must be 0 (or `None`, but please don't do that).
* `topics.RemoteTelemetry`: the ``max_history`` constructor argument is deprecated and should not be specified.
  If specified then it must be 0 (or `None`, but please don't do that).

Changes:

* Implemented authorization support, though that is off by default for now.
  This will not be complete until ts_sal has full support.
* Simplified the simulation support in CSCs, as explained in Deprecations above.
* Added ``--loglevel`` and ``--version`` arguments to `BaseCsc`\ 's command-line argument parser.
* `CscCommander` now rounds float arrays when displaying events and telemetry (it already rounded float scalars).
* Added support for running without a durability service:
  set environment variable ``LSST_DDS_HISTORYSYNC`` to a negative value to prevent waiting for historical data.
* Added the `get_opensplice_version` function.
* If a command is acknowledged with ``CMD_INPROGRESS`` then the command timeout is extended by the ``timeout`` value in the acknowledgement.
  Thus a slow command will need a long timeout as long as command issues a ``CMD_INPROGRESS`` acknowledgement with a reasonable ``timeout`` value.
* Added the ``settingsToApply`` argument to `BaseCscTestCase.check_standard_state_transitions`,
  to allow testing CSCs that do not have a default configuration.
* Environment variable ``LSST_DDS_IP`` is no longer used.
* The ``private_host`` field of DDS topics is no longer read nor set.
* Updated the git pre-commit hook to prevent the commit if black formatting needed.
  This encourages the user to properly commit the necessary reformatting.
* Update ``Jenkinsfile`` to disable concurrent builds and clean up old log files.
* Removed the ``.travis.yml`` file because it duplicates testing done in Jenkins.
* Use `asynco.create_task` instead of deprecated `asyncio.ensure_future`.
* Read topics now use ``DDS_READ_QUEUE_LEN`` as the default value for ``queue_len``.
  They have the same value, but this makes it easier and safer to change ``DDS_READ_QUEUE_LEN`` in future.

Requirements:

* ts_idl 1.3 (older versions might work but have not been tested)
* ts_xml 6.1 (older versions might work but have not been tested)
* IDL files for Test, Script, and LOVE generated by ts_sal 4.2 or later
* SALPY_Test generated by ts_sal 4.2 or later

v5.17.2
=======

Changes:

* Work around a bug in licensed OpenSplice 6.10.4 and 6.10.3 (case 00020647).
  The workaround is compatible with the community edition of OpenSplice 6.9.190705.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.17.1
=======

Changes:

* Bug fix: `BaseCscTestCase.check_bin_script` now sets a random ``LSST_DDS_DOMAIN``, just like ``make_csc``.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.17.0
=======

Changes:

* Added the `CscCommander.start` method and the ``--enable`` command-line flag.
* Added the `SalInfo.name_index` property.
* Made `SalInfo` an async contextual manager. This is primarily useful for unit tests.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.16.0
=======

Changes:

* Add the ``filter_ackcmd`` argument to `ReadTopic`\ 's constructor.
* Improve Jenkins.conda cleanup.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.15.2
=======

Changes:

* Made `RemoteCommand.next` capable of being called by multiple coroutines at the same time.
  This change should also eliminate a source of index errors.
* Bug fix: two tests in ``test_topics.py`` failed if ``LSST_DDS_IP`` was defined.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.15.1
=======

Changes:

* Updated for compatibility with ts_sal 4.2, while retaining compatibility with 4.1
  This required a small change to one unit test.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.15.0
=======

Changes:

* Add `angle_wrap_center` and `angle_wrap_nonnegative` functions.
* Broke the test of black formatting out into its own test file ``test_black.py``,
  to make it easier to copy into other packages.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.14.0
=======

Changes:

* Add ``create`` and ``profile`` arguments to `AsyncS3Bucket`\ 's constructor.
* Add ``other`` and ``suffix`` arguments to `AsyncS3Bucket.make_key`.
* Change `current_tai`, `current_tai_from_utc`, `tai_from_utc`, and `tai_from_utc_unix` to return `float`.
    Formerly they returned a `numpy.float64` scalar (though `current_tai` returned a `float` if using ``CLOCK_TAI``).
* Add ``timeout`` argument to `BaseCscTestCase.make_csc` to handle CSCs that are very slow to start.
* Added minimal compatibility with ts_xml 5.2: the new generic ``setAuthList`` command.
  `Controller` can be constructed, but the command is not yet supported.
* Sped up ``test_csc.py`` by reducing a needlessly long timeout introduced in v5.12.0.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.13.1
=======

Changes:

* Enable test of IDL topic metadata for array fields. This requires IDL files generated by ts_sal 4.1 or later.
* Make some improvements to ``setup.py`` to add requirements.
* Add build/upload pypi package to Jenkinsfile.conda.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE generated by ts_sal 4.1 or later
* SALPY_Test generated by ts_sal 4.1 or later

v5.13.0
=======

Backwards incompatible changes:

* `topics.RemoteCommand.set` and `topics.RemoteCommand.set_start` now start from a fresh data sample,
  rather than using the parameters for the most recent command (``self.data``) as defaults.
  This makes behavior easier to understand and avoids unpleasant surprises.
  It should affect very little code, since most code specifies all parameters for each call.

Other changes:

* `current_tai` now uses the system TAI clock, if available (only on Linux) and if it gives a reasonable time.
  Salobj logs a warning such as ``current_tai uses current_tai_from_utc; clock_gettime(CLOCK_TAI) is off by 37.0 seconds``
  if CLOCK_TAI does not give a reasonable time.
  This warning indicates that salobj is computing TAI from the standard UTC-ish system clock;
  that time will be accurate on most days, but it will be off by up to a second on the day of a leap second.
* `set_summary_state` now accepts ``settingsToApply=None``.
  Formerly it was not supported, but might work.
* Improved IO errors handling while accessing schema, labels and configuration
  file in `ConfigurableCsc`.
* `ConfigurableCsc.get_default_config_dir` renamed to
  `ConfigurableCsc._get_default_config_dir`.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.12.0
=======

Backwards incompatible changes:

* Many methods of topics in `Remote`\ s now raise `RuntimeError` if the remote has not yet started.
  This may cause some code (especially unit tests) to fail with a `RuntimeError`.
  The fix is to make sure the code waits for `Remote.start_task` before trying to read data or issue commands.
  In unit tests consider using ``async with salobj.Remote(...) as remote:``.
  The methods that raise are:

  * Data reading methods: `topics.ReadTopic.has_data`, `topics.ReadTopic.aget`,  `topics.ReadTopic.get`,
    `topics.ReadTopic.get_oldest`, and `topics.ReadTopic.next`.
  * Command issuing methods: `topics.RemoteCommand.start` and `topics.RemoteCommand.set_start`.

Other changes:

* Fixed an error in `name_to_name_index`: it could not handle names that contained integers (DM-24933).
* Fixed an error in `BaseCscTestCase.make_csc`: ``log_level`` was ignored after the first call, and also ignored if the level was greater than (verbosity less than) WARNING.
* Improved `BaseCscTestCase.make_csc` to allow ``log_level=None`` (do not change the log level) and make that the default.
* Update `BaseScript.start` to wait for its remotes to start.
* Update `CscCommander` to include the received time as part of event and telemetry output.
* Improved the error message from `BaseCscTestCase.assert_next_sample` to specify which field failed.
* Improved tests/test_speed.py:

    * Fixed a bug: the measurement "salobj.CreateClasses" was reported as the inverse of the correct value.
    * Do not fail the read speed measurements if samples are lost; writing is faster than reading, so some loss is likely.
      Instead, print the number of samples lost.
    * Improve the measurement "salobj.ReadTest_logLevel" by ignoring an extra logLevel event output by `Controller`.
    * Be more careful about shutting down the topic writer subprocess.
      This eliminates a warning about an unclosed socket.
    * Reduced the number of samples read and written, since it doesn't affect the measurements,
      speeds up the test, and may reduce lost samples.
    * Removed the combined read/write speed test because it is redundant with the tests added in v5.11.0.
* Minor improvements to ``test_salobj_to_either.py`` and ``test_salpy_to_either.py``,
  including printing how long it takes to create the listeneners,
  which is an upper limit (and decent approximation) of how long it waits for historical data.
* Made time limits in unit tests more generous and simpler.
  This should help test robustness on computers that are slow or starved for resources.
* Fixed flake8 warnings about f strings with no {}.
* Removed deprecated ``sudo: false`` entry from ``.travis.yml``, in order to allow github checks to pass once again.
* Modified `assert_black_formatted` to ignore ``version.py``.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.11.0
=======

Major changes:

* Update CscCommander to support custom commands and to run commands in the background.
* Add new speed tests for issuing commands, reading small and large topics, and writing small and large topics.
  Results of the speed tests are uploaded to SQuaSH by Jenkins.
* Add new function `assert_black_formatted` to simplify making sure code remains formatted with ``black``,
  and a unit test that calls the function.
* Increased the shutdown delay in `Controller` from 0.5 seconds to 1 second,
  in order to give `Remote`\ s a bit more time to read final SAL/DDS messages.
  This may require tweaking timeouts in unit tests that wait for a controller to quit.

Other changes:

* Update the CSC documentation to move the details for configurable CSCs to a new section.
* Change `SalInfo` to only set the log level if it is less verbose than `loggint.INFO`.
  That makes it easier to set a more verbose level in unit tests.
* Update a unit test for compatibility with the pending release of ts_xml 5.2.
* Made ``test_salpy_to_either.py`` more robust by increasing the polling rate for messages.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.10.0
=======

Major changes:

* Sped up DDS message read and write by a factor of 8, as reported by ``tests/test_speed.py``.
  This was done by speeding up `tai_from_utc`, which turned out to be the bottleneck.
* Add function `tai_from_utc_unix`, which does most of the work for `tai_from_utc`.

Minor changes:

* Improved the Jenkins file handling for building and uploading the documentation.
  If building the documentation fails then the Jenkins job fails.
  If uploading the documentation fails then the Jenkins job is marked as unstable.

Notes:

* `tai_from_utc` and `astropy_time_from_tai_unix` will be deprecated once we upgrade to a version of AstroPy that supports TAI seconds directly.
  That change has been committed to the AstroPy code base.
  The new function `tai_from_utc_unix` will remain.
* salobj now uses a daemon thread to maintain an internal leap second table.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.9.0
======

Backwards incompatible changes:

* The arguments have changed slightly for `AsyncS3Bucket.make_bucket_name` and `AsyncS3Bucket.make_key` and the returned values are quite different.
  We changed our standards because it turns out that large numbers of buckets are a problem for Amazon Web Services (AWS).

Major changes:

* Add a ``timeout`` argument to `BaseCscTestCase.check_standard_state_transitions`.
* Update `BaseCsc.start` to output the ``softwareVersions`` event.
* Update `ConfigurableCsc` to output the ``settingsApplied`` event.

Minor changes:

* Allow the ``SALPY_Test`` library to be missing: skip the few necessary unit tests if the library is not found.
* The Jenkins job now builds and uploads the documentation (even if unit tests fail).
* Improve the reliability of ``tests/test_salobj_to_either.py`` by increasing a time limit.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.8.0
======

Major changes:

* Improved `AsyncS3Bucket`:

    * Read environment variable ``S3_ENDPOINT_URL`` to obtain the endpoint URL.
      This allows use with non-AWS S3 servers.
    * Added support for running a mock S3 server: a new ``domock`` constructor argument and `AsyncS3Bucket.stop_mock` method.
      This is intended for CSCs running in simulation mode, and for unit tests.
    * Added static method `AsyncS3Bucket.make_bucket_name`.
    * Added static method `AsyncS3Bucket.make_key`.

* Improved `BaseCscTestCase`:

    * Added argument ``skip_commands`` to `BaseCscTestCase.check_standard_state_transitions`.
    * Added argument ``**kwargs`` to `BaseCscTestCase.make_csc` and `BaseCscTestCase.basic_make_csc`.
    * Changed argument ``*cmdline_args`` to ``cmdline_args`` for `BaseCscTestCase.check_bin_script`, for clarity.

Other changes:

* Added a :ref:`lsst.ts.salobj-configuration` section to the documentation.
* Added missing unit test for `topics.QueueCapacityChecker`.
* Standardized the formatting for attributes documented in the Notes section for some classes.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.7.0
======

Major changes:

* Added `astropy_time_from_tai_unix` function.
* Added `CscCommander` to support exercising CSCs from trivial command-line scripts (DM-23771).
* Added ``bin/zrun_test_commander.py`` to exercise `CscCommander`.
* Added `stream_as_generator` to support reading user input from asyncio-based interactive command-line scripts, such as CSC commanders.
* The package is now conda-installable.
* Added constants ``LOCAL_HOST``, ``SECONDS_PER_DAY`` and ``MJD_MINUS_UNIX_SECONDS``.

Other changes:

* Set the ``name`` field of ``logMessage``, if available (DM-23812).
* Fixed two issues in `tai_from_utc` when provided with an `astropy.time.Time`.

    * Using the default value for the ``scale`` argument caused incorrect behavior.
      Now the ``scale`` argument is ignored, as it should be, since astropy time's have their own scale.
    * The behavior on a leap second day was not well documented and differed from `astropy.time`.
      Document it and match `astropy.time`.
* Improved logging for queues filling up, especially the DDS queue (DM-23802).
* Prevent `BaseScript` from being constructed with index=0, because such a script would receive commands for every script (DM-23900).
* Fixed a bug in `ConfigurableCsc.begin_start` that could result in an undefined variable when trying to print an error message.
* Load the astropy leap second table at startup, so the first call to `current_tai` is fast.
* Use `time.monotonic` instead of `time.time` to measure durations.

Requirements:

* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.6.0
======

Major changes:

* Added `BaseConfigTestCase` to support testing configuration files in ts_config_x packages.

Requirements:

* black
* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.5.0
======

Major changes:

* Scripts now launch with master priority 0 (or will, once https://jira.lsstcorp.org/browse/DM-23462 is implemented).
  This should make scripts launch more quickly.

Requirements:

* black
* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.4.0
======

Major changes:

* Add support for the new ``setGroupId`` ``Script``  command to `BaseScript`:

    * Scripts must now have a non-blank group ID before they are run.
    * Add `BaseScript.group_id` property.
    * Add `BaseScript.next_supplemented_group_id` method.
* Changed `BaseScript.do_resume` and `BaseScript.do_setCheckpoints` to asynchronous, so all ``do_...`` methods are asynchronous, for consistency. I did not find any code outside of ts_salobj that was affected, but it is a potentially breaking change.
* Output fields added to the ``logMessage`` event in ts_xml 4.7.
* Code formatted by ``black``, with a pre-commit hook to enforce this. See the README file for configuration instructions.

Minor changes:

* Fix bugs in `BaseCscTestCase.check_bin_script` and update ``test_csc.py`` to call it.
* Removed our local copy of ``ddsutil.py``.

Requirements:

* black
* ts_idl 1
* ts_xml 4.7
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.3.0
======

Major changes:

* Add `BaseCscTestCase` as a useful base class for CSC unit tests.
  Update the unit tests to use it.

Minor changes:

* `DefaultingValidator` now handles defaults in sub-objects (one level deep).
* CSCs will now reject optional generic commands if not implemented (meaning there is no ``do_``\ *command* method for them), instead of silently ignoring them.
  The optional generic commands are ``abort``, ``enterControl``, ``setValue``, and the deprecated command ``setSimulationMode``.
* The ``action`` argument of `BaseCsc.assert_enabled` is now optional. There is no point to setting it when calling it from ``do_``\ *command* methods as the user knows what command was rejected.
* If a command is rejected because a CSC is in ``FAULT`` state, the error message contains the current value of the ``errorReport`` field of the ``errorCode`` event.
* `SalInfo` could not be created for a SAL component that had no commands (because such a component also has no ackcmd topic).

Deprecated APIs:

* ``lsst.ts.salobj.test_utils`` is deprecated. Please use ``lsst.ts.salobj`` instead.


Requirements:

* ts_idl 1
* ts_xml 4.6
* IDL files for Test, Script, and LOVE.
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.2.1
======

Fix a call to `warnings.warn` in `Domain`.

Requirements:

* ts_idl 1
* ts_xml 4.6
* IDL files for Test and Script
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.2.0
======

Major changes:

* CSCs no longer support the ``setSimulationMode`` command, as per RFC-639.

Deprecated APIs:

* BaseCsc and ConfigurableCsc: the ``initial_simulation_mode`` constructor argument is deprecated in favor of the new ``simulation_mode`` argument.
  It is an error to specify both.

v5.1.0
======

Major changes:

* Provide IDL metadata, including descriptions of topics and descriptions and units of fields, via a new `SalInfo` ``metadata`` attribute, an instance of `IdlMetadata`.
  Some of the metadata is only available in IDL files built with SAL 4.6.
* Add the `AsyncS3Bucket` class for writing to Amazon Web Services s3 buckets.

Minor changes:

* Change a link in the doc string for `BaseCsc.handle_summary_state` to avoid Sphinx errors in subclasses in other packages.
* Add a ``done_task`` attribute to `Domain`.
* Add an ``isopen`` attribute to `Controller`.
* Improve close methods for `Domain`, `SalInfo`, `Controller` and `Remote` to reduce warnings in unit tests.
  Subsequent calls wait until the first call finishes and `SalInfo` allows time for its read loop to finish.

Deprecated APIs:

* ``SalInfo.idl_loc`` should now be ``SalInfo.metadata.idl_path``.

Requirements:

* ts_idl 1
* IDL files for Test and Script
* SALPY_Test generated by ts_sal 4 (for unit tests)

v5.0.0
======

Update for ts_sal v4. This version cannot communicate with ts_sal v3 or ts_salobj v4 because of changes at the DDS level:

* The ``ackcmd`` topic has new fields that distinguish acknowledgements for commands sent by one `Remote` from those sent by another.
* Command topics and the ``ackcmd`` topic now have ``volatile`` durability instead of ``transient``.
  This means they cannot read late-joiner data, which eliminates a source of potential problems from stale commands or command acknowledgements.
* The DDS queues now hold 100 samples instead of 1000.

Another backward incompatible change is that the setSimulationMode command can no only be issued in the STANDBY state.
This makes it much easier to implement simulation mode in CSCs that connect to external controllers,
because one can make the connection in the appropriate mode when in DISABLED or ENABLED state, without having to worry about changing it.
This change may break some existing unit tests for CSCs that support simulation mode.

Deprecated APIs:

* Specifying ``code=None`` for `BaseCsc.fault` is deprecated. Please always specify an error code so the ``errorCode`` event can be output.
* `BaseCsc.main` and `BaseScript.main` are deprecated. Please replace ``cls.main(...)`` with ``asyncio.run(cls.amain(...))``.
  This makes it much clearer that the call may not return quickly, avoids explicitly creating event loops, and takes advantage of the (new to Python 3.7) preferred way to run asynchronous code.
* Setting ``BaseCsc.summary_state`` is deprecated.
  In unit tests use the standard state transition commands or call the `set_summary_state` function.
  In CSCs you should not be setting summary state directly; of the existing CSC code I've seen,
  most of it sends the CSC to a FAULT state, for which you should call `BaseCsc.fault`,
  and the rest doesn't need to set the summary state at all.
* Script commands ``setCheckpoints`` and ``setLogLevel`` are deprecated.
  Specify checkpoints and log level using the new ``pauseCheckpoint``, ``stopCheckpoint`` and ``logLevel`` fields in the ``configure`` command.
* Code that constructs a `Remote` or `Controller` without a running event loop should be rewritten because it will break when we replace the remaining usage of `asyncio.ensure_future` with the preferred `asyncio.create_task`. For example:

  .. code-block:: python

    csc = MyCscClass(...)
    asyncio.get_event_loop().run_until_complete(csc.done_task)

  can be replaced with (see `BaseCsc.make_from_cmd_line` to add command-line arguments):

  .. code-block:: python

    asyncio.run(MyCscClass.amain(...))

New capabilities:

* Add function `current_tai` to return the current time in TAI unix seconds (LSST's standard for SAL timestamps).
* Enhance function `tai_from_utc` to support alternate formats for UTC using new argument ``format="unix"``.
* Add `topics.ReadTopic.aget` to return the current sample, if any, else wait for the next sample (DM-20975).
* Add coroutine ``BaseCsc.handle_summary_state``.
  This is the preferred way to handle changes to summary state instead of overriding synchronous method `BaseCsc.report_summary_state`.
* Add property ``BaseCsc.disabled_or_enabled`` which returns true if the current summary state is `State.DISABLED` or `State.ENABLED`.
  This is useful in ``BaseCsc.handle_summary_state`` to determine if you should start or stop a telemetry loop.
* Add ``result_contains`` argument to `assertRaisesAckError`.
* Enhance `topics.ControllerCommand` automatic acknowledgement for callback functions so that the ``ack`` value is `SalRetCode`.CMD_ABORTED if the callback raises `asyncio.CancelledError` and `SalRetCode`.CMD_TIMEOUT if the callback raises `asyncio.TimeoutError`.
* `Controller.start` now waits for all remotes to start (except those constructed with ``start=False``, which is rare).
* Added ``start_called`` attribute to `SalInfo`, `Controller` and `Remote`.

Other improvements:

* Fix support for environment variable ``LSST_DDS_IP``.
  The value is now a dotted IP address; formerly it was an integer.
* Improve error handling when specifying a non-zero index for a non-indexed SAL component (DM-20976).
  The `SalInfo` constructor will now raise an exception.
* Improve error handling in `BaseCsc.fault`. Report the problem and continue if the error code is not an integer, or if `BaseCsc.report_summary_state` fails.
* The unit tests use the ``asynctest`` package, which is pip installable.
* The documentation for `BaseCsc.main` now recommends specifying ``index=None or 0`` for non-indexed components, instead of ``None or False``, in order to match standard usage in ts_salobj.
  All three values worked, and continue to work, but no existing code used `False`.
* Minor improvements to version handling:

    * Set ``lsst.ts.salobj.__version__`` to "?" if running directly from source and there is no ``version.py`` file generated by ``setup.py`` or ``scons``.
    * Update ``doc/conf.py`` to get ``__version__`` from ``lsst.ts.salobj`` instead of ``lsst.ts.salobj.version``.
* Stop reading dead topics because ts_sal 4 no longer disposes of any samples immediately after writing.
  This removes a workaround added in v4.3.0.
* Add this revision history.

Existing code is unlikely to require any changes to transition from salobj v4 to v5.

Communicates with ts_sal v4.

Requirements:

* ts_idl
* IDL files for Test and Script
* SALPY_Test generated by ts_sal v4 (for unit tests)

v4.5.0
======

Minor updates for ts_watcher and ts_salkafka:

* Add several name attributes to topics:

    * ``sal_name``: the name used by SAL for a topic, e.g. "logevent_summaryState".
    * ``attr_name``: the name used by ts_salobj for topic attributes of `Remote` and `Controller` e.g. "evt_summaryState".
    * ``dds_name``: the name used by DDS for a topic, e.g. "Test_logevent_summaryState_90255bf1".
    * ``rev_code``: the revision code that SAL appends to DDS topic names, e.g. "90255bf1".

* Remove the ``attr_prefix`` attribute from topics.

Communicates with ts_sal v3.10 (but not 3.9).

Requirements:

* ts_idl
* IDL files for Test and Script
* SALPY_Test generated by ts_sal v3.10 (for unit tests)

v4.4.0
======

Minor updates for ts_watcher:

* Add support to `Remote` for adding topics after the object is constructed:

    * Change the meaning of constructor argument ``include=[]`` to include no topics.
      Formerly it would include all topics.
    * Add constructor argument ``start`` which defaults to True for backwards compatibility.
      Set it False if you want to add topics after constructing the remote.

* Add function `name_to_name_index` for parsing SAL component names of the form ``name[:index]``.
* Add ``attr_prefix`` attribute to `topics.BaseTopic`.
  Warning: this was replaced by ``attr_name`` in v4.5.0.

Communicates with ts_sal 3.10 (but not 3.9).

Requirements:

* ts_idl
* IDL files for Test and Script
* SALPY_Test generated by ts_sal v3.10 (for unit tests)

v4.3.1
======

Make the unit test pass more reliably.

Warning: the unit tests only pass reliably if run using ``pytest``.
I still see a failure roughly 1/4 of the time when run using ``scons``.
This is probably a side effect of enabling code coverage analysis.

Other changes:

* Make ``scons`` optional by moving bin scripts from ``bin.src/`` to ``bin/`` and making ``version.py`` optional.
* Modify `BaseCsc.set_summary_state` to return a list of summary states.
  This is mostly for the sake of unit tests but it also tells callers what state the CSC started in.


Requirements:

* ts_idl
* IDL files for Test and Script
* SALPY_Test generated by ts_sal v3.10 (for unit tests)

v4.3.0
======

The first version that is truly compatible with ts_sal 3.10.

Fix an incompatibility with SAL 3.10:

* salobj could not reliably read ackcmd and command topics sent by SAL 3.10 because SAL 3.10 disposes those samples immediately after writing.
  Fixed by reading dead samples for those topics.
  This is intended as a temporary change until ts_sal is updated to not dispose samples after writing.
* Added a unit test for salobj<->SAL communication.
  Thus ts_sal is now an optional dependency of ts_salobj.

Requirements:
- ts_idl 0.1
- SALPY_Test generated by ts_sal 3.10 (for unit tests)

v4.2.0
======

Warning: do not use this version because it is not compatible with ts_sal. Use v4.3.0 or later.

Add BaseScript (moved from ts_scriptqueue).


v4.1.1
======

Warning: do not use this version because it is not compatible with ts_sal. Use v4.3.0 or later.

Do not warn about the config labels file if empty.
Only warn if the config labels file has data and that data cannot be parsed as a dict.

Other changes:

* Update log.warn to log.warning to fix deprecation warnings.


v4.1.0
======

Warning: do not use this version because it is not compatible with ts_sal. Use v4.3.0 or later.

Add ``evt_max_history`` and ``tel_max_history arguments`` to `Remote` constructor.

v4.0.0
======

Warning: do not use this version because it is not compatible with ts_sal. Use v4.3.0 or later.

Compete rewrite to use OpenSplice dds instead of SALPY libraries generated by ts_sal.
For more information see https://community.lsst.org/t/changes-in-salobj-4-the-dds-version/3701

To generate IDL files use command-line script ``make_idl_files.py`` which is available in ts_sal 3.10.
For example::

    make_idl_files.py Test Script
