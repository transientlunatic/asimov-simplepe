asimov-simplepe
================

``asimov-simplepe`` is a plugin for `Asimov <https://asimov.docs.ligo.org/asimov/>`_
0.7+ that integrates `simple-pe <https://git.ligo.org/stephen-fairhurst/simple-pe>`_,
a rapid, metric/Fisher-matrix-based parameter estimation code for gravitational-wave
signals from compact binary coalescences. Once installed, the plugin is discovered
automatically via Asimov's entry-point registry -- no extra configuration is
required.

**What it does**

* Writes a small ``trigger_parameters.json`` file (the approximate event parameters
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
   echo "setuptools<82" > constraints.txt  # see the pkg_resources note below
   echo "numpy<2" >> constraints.txt        # see the numpy note below
   pip install -c constraints.txt "setuptools<82" "numpy<2"
   pip install -c constraints.txt git+https://git.ligo.org/stephen-fairhurst/simple-pe.git
   pip install asimov-simplepe

From source:

.. code-block:: bash

   conda install -c conda-forge pycbc lalsuite
   echo "setuptools<82" > constraints.txt  # see the pkg_resources note below
   echo "numpy<2" >> constraints.txt        # see the numpy note below
   pip install -c constraints.txt "setuptools<82" "numpy<2"
   pip install -c constraints.txt git+https://git.ligo.org/stephen-fairhurst/simple-pe.git
   git clone https://github.com/transientlunatic/asimov-simplepe.git
   cd asimov-simplepe
   pip install -e ".[docs,test]"

.. note::

   This plugin's bundled template's config keys and value formats are
   confirmed directly against a real, live ``simple_pe_pipe --help`` and a
   real successful DAG build in its own end-to-end CI. Its output-file
   detection (``samples()``) is still an unconfirmed best-effort guess,
   though -- see the *Compatibility* note in the README if you hit a
   mismatch there (or anywhere else) against a real ``simple_pe_pipe``
   release.

.. note::

   ``simple_pe_pipe`` imports ``pycbc.waveform``, whose
   ``retrieve_waveform_plugins()`` does a bare ``import pkg_resources`` (see
   `simple-pe issue #29 <https://git.ligo.org/stephen-fairhurst/simple-pe/-/issues/29>`_,
   still open upstream). ``setuptools`` removed the bundled
   ``pkg_resources`` module starting with 82.0.0 (confirmed directly:
   81.0.0 still provides it, 82.0.0 doesn't), so ``simple_pe_pipe`` fails
   to even import with ``ModuleNotFoundError: No module named
   'pkg_resources'`` against an unpinned (or too-recent) ``setuptools`` --
   confirmed directly via this plugin's own end-to-end CI run. A bare
   ``pip install "setuptools<82"`` isn't enough on its own, either:
   installing ``simple-pe`` in a *separate* ``pip install`` right after it
   can silently re-resolve ``setuptools`` back past 82 as one of its own
   transitive dependencies (also confirmed directly). A constraints file
   applied to both commands, as shown above, is what actually holds the
   pin.

.. note::

   ``simple_pe_filter``'s own ``load_trigger_parameters_from_file()`` wraps
   the loaded trigger-parameters dict in ``SimplePESamples`` (a
   pesummary-style samples container built for posterior *chains*, so even
   a single scalar comes back as a shape-``(1,)`` array rather than a true
   0-d array) before
   ``simple_pe.io.io.estimate_data_length_from_template_parameters`` does
   ``int(2**(np.ceil(np.log2(wf_len))))`` on a value derived from it.
   NumPy hard-errors this exact implicit shape-``(1,)``-to-scalar
   conversion since 2.0 (only a ``DeprecationWarning`` before that):
   ``TypeError: only 0-dimensional arrays can be converted to Python
   scalars``, hit on every real analysis regardless of channel mode --
   confirmed directly via this plugin's own end-to-end CI on the real
   ``filter`` DAG node. Pinning ``numpy<2`` (alongside every pip install
   here, for the same re-resolution reason as ``setuptools`` above) keeps
   it a warning instead of a crash without touching ``simple-pe``'s own
   source.

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
          H1: GWOSC
          L1: GWOSC
        asd:
          H1: /path/to/aLIGO_asd.txt
          L1: /path/to/aLIGO_asd.txt
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

   .. note::

      The rendered ini always sets ``peak_finder`` (default ``metric``,
      overridable via ``production.meta['peak_finder']``, e.g.
      ``scipy``). This isn't cosmetic: ``simple_pe_pipe``'s real
      ``--peak_finder`` defaults to an *empty list*, and its DAG-building
      code creates every actual analysis stage (match-filter, metric,
      corner-plot, PESummary) inside a loop over that list -- an empty
      list means the loop runs zero times and the DAG silently ends up
      containing only its ``datafind`` job, with no error at all.
      Confirmed directly via this plugin's own e2e CI.

   .. note::

      ``neffective`` is unset by default -- ``simple_pe_analysis`` uses
      its own default (1000 effective samples, confirmed directly from
      its real source), the right choice for real production use.
      Override it via ``production.meta['neffective']``, e.g. ``20``, to
      cap a slow real analysis's convergence target down for a quick
      smoke test (this plugin's own e2e test does exactly that -- a real
      analysis against real GW150914 data, even with a higher-mode-
      capable, non-precessing approximant, genuinely needs well over 25
      wall-clock minutes on a single CPU to converge to 1000 effective
      samples, confirmed directly via this plugin's own e2e CI).

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

Strain data is read from a production's ``data`` meta-data. ``data.channels``
is the channel name *without* the leading ``IFO:`` (this plugin adds that
itself when rendering the ini); ``data.asd`` is a path to a real, two-column
(frequency, ASD) text file -- confirmed directly from ``--help`` ("ASD files
to use for the analysis") and from this plugin's own e2e CI: there is no
analytic-PSD-model-name shortcut in the CLI, it always opens whatever string
is given as a literal file path.

.. code-block:: yaml

   data:
     channels:
       H1: DCS-CALIB_STRAIN_CLEAN_C01
       L1: DCS-CALIB_STRAIN_CLEAN_C01
     asd:
       H1: /path/to/H1_asd.txt
       L1: /path/to/L1_asd.txt

``simple_pe_pipe`` also recognises two special ``data.channels`` values,
confirmed directly from its own ``--help`` text: ``GWOSC``, to read public
GWOSC open data instead of a private frame channel -- this plugin's own
end-to-end test uses this, against GW150914's real data, paired with a
real ASD file (generated at CI time from pycbc's analytic
``aLIGOZeroDetHighPower`` model) since a PSD is needed for the
Fisher-matrix/SNR calculation regardless of where the strain data comes
from -- and ``INJ``, to have ``simple_pe_pipe`` simulate an injection
itself rather than reading any real strain data at all -- no datafind
access needed. Whenever any interferometer uses ``INJ``,
:meth:`before_config() <asimov_simplepe.simplepe.SimplePE.before_config>`
also writes an ``injection.json`` file from the production's ``trigger``
metadata (masses/spins in the underscored LIGO convention
``mass_1``/``spin_1z``/etc, plus ``distance``/``ra``/``dec``/``psi``/``time``)
and the ini references it -- confirmed directly from
``simple_pe_datafind``'s real source that this is required unconditionally
whenever any channel is ``INJ``:

.. code-block:: yaml

   data:
     channels:
       H1: INJ
     asd:
       H1: /path/to/aLIGO_asd.txt

.. warning::

   ``INJ`` mode currently hits a genuine upstream ``simple-pe`` bug once
   ``write_converted_injection_parameters()`` runs: a ``SimplePESamples``-
   wrapped value eventually produces a NaN GPS time, sending LALSuite's
   ``XLALGPSSetREAL8()`` into what is for all practical purposes an
   infinite loop -- confirmed directly via this plugin's own e2e CI (see
   ``CHANGELOG.md`` for the full trail). This plugin's own code fully
   supports ``INJ`` (unit-tested) and will use it correctly once this is
   fixed upstream, but its own e2e test uses ``GWOSC`` instead to avoid
   depending on that fix.

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

This is also why the bundled ``configs/simplepe.ini`` template sets
``disable_pesummary = True``: left at its default ``False``,
``simple_pe_pipe``'s own DAG bakes a full PESummary post-processing job
into itself as a child of the analysis node (confirmed directly from its
real ``main()`` source) -- duplicating whatever separate, ``needs:``-linked
PESummary production is meant to handle post-processing, and running
PESummary twice for no benefit.

.. note::

   **Known issue (root-caused, not a permanent blocker):**
   ``simple_pe_pipe``'s own ``analysis`` stage can hit a real crash
   before producing a posterior samples file: PESummary's subdominant-
   multipole rejection-sampling reweighting
   (``pesummary.core.reweight.rejection_sampling()``, called unconditionally
   from ``simple_pe.param_est.pe.reweight_based_on_observed_snrs()``) has no
   guard against a non-finite weight, and raises ``OverflowError: Range
   exceeds valid bounds`` when one occurs. This is a *different* use of
   PESummary than the ``disable_pesummary``/post-processing job above: it
   happens inside ``simple_pe_analysis`` itself, as part of generating
   posterior samples from the Fisher-matrix point estimate, and isn't
   gated by ``disable_pesummary`` at all.

   This first looked like a genuine, unfixable upstream numerical-
   robustness bug -- but root-causing it directly via this plugin's own
   e2e CI (see ``CHANGELOG.md`` for the full trail) found the real
   trigger: the reweighting step unconditionally measures the *observed*
   SNR in the (3,3)/(4,4) higher multipoles and in precession, regardless
   of whether the configured ``waveform.approximant`` can represent them.
   Against a dominant-mode-only, non-precessing approximant (e.g.
   ``IMRPhenomD``), those observed SNRs come back ``NaN``, and the
   reference distribution built from them underflows to exactly ``0.0``
   probability for essentially every sample once zeroed -- not a rare
   outlier, but systemic corruption. Using an approximant that actually
   supports higher modes (e.g. ``IMRPhenomXHM`` or ``IMRPhenomXPHM`` --
   the latter is ``simple_pe_filter``'s/``simple_pe_analysis``'s own
   ``--approximant`` default) avoids this entirely, confirmed directly:
   no ``OverflowError`` (or any other crash) recurs. ``simple-pe``'s own
   real-waveform interpolation grids do make a precessing+higher-mode
   approximant meaningfully slower to converge than a dominant-mode-only
   one, though -- see the ``neffective`` note above for how this
   plugin's own e2e test manages that.

   **Defensive safety net.** ``simple-pe``'s
   ``reweight_based_on_observed_snrs()``/PESummary's
   ``rejection_sampling()`` still have no guard against a non-finite
   weight even with a correct approximant choice -- a real analysis
   could still hit a similarly degenerate weight for other reasons this
   plugin hasn't characterised.
   ``scripts/patch_simple_pe_reweight_guard.py`` patches an installed
   ``simple-pe``'s ``reweight_based_on_observed_snrs()`` in place to zero
   out any non-finite weight before it reaches ``rejection_sampling()``
   -- treating a numerically broken sample as zero-probability (rejected)
   rather than crashing, or (worse) treating it as certain. The correct
   fix still belongs upstream (in either ``simple-pe`` or ``pesummary``,
   since any of ``rejection_sampling()``'s other callers could hit the
   same crash); this is deliberately just a stopgap. Run it once, in the
   same Python environment
   ``simple_pe_analysis`` runs in, right after installing ``simple-pe``
   and before running any real analysis:

   .. code-block:: bash

      python scripts/patch_simple_pe_reweight_guard.py

   It's idempotent (a no-op if already applied) and fails loudly, rather
   than silently doing nothing, if ``simple-pe``'s source has changed
   enough that its exact expected original text can't be found -- see the
   script's own docstring for the full rationale. This can't be applied
   automatically by ``asimov_simplepe`` itself at import time: the buggy
   code runs inside ``simple_pe_analysis``'s own HTCondor subprocess, a
   completely separate Python process from asimov's, so a plugin-level
   monkeypatch would never reach it -- it has to be applied to the
   installed ``simple-pe`` package directly, in whatever environment
   actually runs the analysis jobs. This plugin's own CI applies the
   exact same script (see
   ``.github/actions/setup-simplepe-env/action.yml``).

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
