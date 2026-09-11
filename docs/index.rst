asimov-simplepe
================

``asimov-simplepe`` is a plugin for `Asimov <https://asimov.docs.ligo.org/asimov/>`_
0.7+ that integrates `simple-pe <https://git.ligo.org/stephen-fairhurst/simple-pe>`_,
a rapid, metric/Fisher-matrix-based parameter estimation code for gravitational-wave
signals from compact binary coalescences. Once installed, the plugin is discovered
automatically via Asimov's entry-point registry -- no extra configuration is
required.

**What it does**

* Writes a small ``trigger_parameters.ini`` file (the approximate event parameters
  ``simple_pe_pipe`` uses to seed its local optimisation), then renders a
  ``simple_pe_pipe`` config file from a production's meta-data (waveform, data,
  likelihood), using this plugin's bundled
  :attr:`config_template <asimov_simplepe.simplepe.SimplePE.config_template>` -- or
  picks up a hand-written ``.ini`` already committed to the event repository.
* Runs ``simple_pe_pipe`` to build a real HTCondor DAG, then submits it to an
  HTCondor or Slurm scheduler via Asimov's scheduler-agnostic API.
* Once the run completes, advertises its samples (via ``collect_assets()``) for any
  downstream production that declares a ``needs:`` dependency on it -- for example a
  `asimov-pesummary <https://github.com/etive-io/asimov-pesummary>`_ post-processing
  production. This plugin does not submit that job itself; see *Post-processing*
  below.
* Resubmits a failed or evicted job from its DAGMan rescue file, rather than
  restarting from scratch.

Installation
------------

``simple-pe`` itself must be installed separately -- this plugin shells out to the
``simple_pe_pipe`` executable rather than importing ``simple_pe``, so it isn't
pulled in as a Python dependency. It isn't currently distributed on PyPI or
conda-forge, so install it from its GitLab repository (it depends on ``pycbc`` and
``lalsuite``, both available from conda-forge):

.. code-block:: bash

   conda install -c conda-forge pycbc lalsuite
   pip install "setuptools<82"  # see the pkg_resources note below
   pip install git+https://git.ligo.org/stephen-fairhurst/simple-pe.git
   pip install asimov-simplepe

From source:

.. code-block:: bash

   conda install -c conda-forge pycbc lalsuite
   pip install "setuptools<82"  # see the pkg_resources note below
   pip install git+https://git.ligo.org/stephen-fairhurst/simple-pe.git
   git clone https://github.com/transientlunatic/asimov-simplepe.git
   cd asimov-simplepe
   pip install -e ".[docs,test]"

.. note::

   ``simple_pe_pipe``'s ini format isn't fully documented publicly. This plugin's
   bundled template and output-file detection are a best-effort match against
   ``simple-pe``'s own public documentation and issue tracker -- see the
   *Compatibility* note in the README if you hit a mismatch against a real
   ``simple_pe_pipe`` release.

.. note::

   ``simple_pe_pipe`` imports ``pycbc.waveform``, whose
   ``retrieve_waveform_plugins()`` does a bare ``import pkg_resources`` (see
   `simple-pe issue #29 <https://git.ligo.org/stephen-fairhurst/simple-pe/-/issues/29>`_,
   still open upstream). ``setuptools`` removed the bundled
   ``pkg_resources`` module starting with 82.0.0 (confirmed directly:
   81.0.0 still provides it, 82.0.0 doesn't), so ``simple_pe_pipe`` fails
   to even import with ``ModuleNotFoundError: No module named
   'pkg_resources'`` against an unpinned (or too-recent) ``setuptools`` --
   confirmed directly via this plugin's own end-to-end CI run. Pin
   ``setuptools<82`` first, as shown above, to work around it.

Tutorial: from a fresh project to posterior samples
----------------------------------------------------

This walks through a complete example.

1. Create a project and point Asimov at your Simple-PE environment:

   .. code-block:: bash

      asimov init "Tutorial Project"
      cd "Tutorial Project"
      asimov configuration update pipelines/environment "$CONDA_PREFIX"

2. Apply an event:

   .. code-block:: yaml

      # event.yaml
      kind: event
      name: GW150914
      interferometers:
        - H1
        - L1
      event time: 1126259462.4
      waveform:
        approximant: IMRPhenomXPHM

   .. code-block:: bash

      asimov apply -f event.yaml

   ``waveform`` lives here, at the event level, rather than being repeated on each
   production: it's real signal metadata shared by everything analysing this event,
   and Asimov inherits event-level meta into every production for it automatically
   (before that production's own blueprint keys are merged on top).

3. Apply a ``simplepe`` production:

   .. code-block:: yaml

      # simplepe-production.yaml
      kind: analysis
      name: simplepe-test
      pipeline: simplepe
      status: ready
      trigger:
        mass1: 36
        mass2: 29
        spin1z: 0.0
        spin2z: 0.0
        ra: 1.95
        dec: -1.27
        distance: 440
      likelihood:
        minimum frequency:
          H1: 20
          L1: 20
      data:
        channels:
          H1: H1:FAKE-STRAIN
          L1: L1:FAKE-STRAIN
        asd:
          H1: aLIGOZeroDetHighPower
          L1: aLIGOZeroDetHighPower
      scheduler:
        accounting group: ligo.dev.o4.cbc.pe.simple_pe

   .. code-block:: bash

      asimov apply -f simplepe-production.yaml -e GW150914
      asimov manage build submit

   ``manage build`` writes the trigger-parameters file and renders
   ``simplepe-test.ini`` from this plugin's bundled
   :attr:`config_template <asimov_simplepe.simplepe.SimplePE.config_template>`
   (unless an ini already exists in the event repository), ``build`` runs
   ``simple_pe_pipe`` to construct the DAG, and ``submit`` submits it.

4. Wait for it to finish, checking status with:

   .. code-block:: bash

      asimov monitor

   Once finished, the posterior samples live somewhere under
   ``working/GW150914/simplepe-test/`` -- see
   :meth:`samples() <asimov_simplepe.simplepe.SimplePE.samples>`.

5. Chain a PESummary post-processing step onto it as its own production, with a
   ``needs:`` dependency on ``simplepe-test``:

   .. code-block:: yaml

      # pesummary-production.yaml
      kind: analysis
      name: simplepe-test-pesummary
      pipeline: pesummary
      status: ready
      needs:
        - simplepe-test
      postprocessing:
        pesummary:
          multiprocess: 2

   .. code-block:: bash

      asimov apply -f pesummary-production.yaml -e GW150914
      asimov manage build submit

   You can apply this at any point, even before ``simplepe-test`` has finished --
   Asimov's own dependency resolution won't actually build and submit
   ``simplepe-test-pesummary`` until ``simplepe-test`` reaches ``finished``, at which
   point PESummary picks up its samples through ``simplepe-test``'s
   ``collect_assets()`` (via ``production._previous_assets()``), with no glue code
   of any kind needed from this plugin. Keep running ``asimov monitor`` to drive
   both productions through to completion; PESummary's output pages land under
   Asimov's configured webroot.

Data
----

Strain data is read from a production's ``data`` meta-data, using the same
conventions as the sibling GW pipeline plugins (``asimov-lalinference``,
``asimov-pycbc``) and `asimov-gwdata <https://github.com/etive-io/asimov-gwdata>`_:

.. code-block:: yaml

   data:
     channels:
       H1: H1:DCS-CALIB_STRAIN_CLEAN_C01
       L1: L1:DCS-CALIB_STRAIN_CLEAN_C01
     asd:
       H1: /path/to/H1_asd.txt
       L1: /path/to/L1_asd.txt

or, for simulated noise (as used by this plugin's own end-to-end test):

.. code-block:: yaml

   data:
     channels:
       H1: H1:FAKE-STRAIN
     asd:
       H1: aLIGOZeroDetHighPower

Status messages
~~~~~~~~~~~~~~~~

``wait``
   The pipeline will ignore the production.

``ready``
   Asimov will attempt to build and submit the DAG.

``running``
   Applied after the DAG is submitted to the cluster.

``stuck``
   Applied when the job is held or an error is detected in the pipeline's execution.

``finished``
   Applied when normal termination of the pipeline is detected (a real, readable
   posterior samples file exists). This is a terminal state as far as this plugin is
   concerned -- see *Post-processing* below for what (if anything) happens next.

Post-processing
----------------

This plugin does not run any post-processing itself, and ``after_completion()``
does nothing beyond marking the production ``finished``. Instead, post-processing
(PESummary or otherwise) is expressed as its own, separate production with a
``needs:`` dependency on the ``simplepe`` production -- see step 5 of the tutorial
above. Asimov's own dependency resolution is what actually builds and submits that
production once this one finishes; this plugin only needs to make its samples
available via ``collect_assets()``, which it always does regardless of whether
anything ever consumes them.

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
