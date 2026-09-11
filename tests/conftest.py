"""Pytest configuration and fixtures."""

import tempfile
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_production():
    """Create a mock production object for testing."""
    production = MagicMock()
    production.name = "TestProduction"
    production.pipeline = "simplepe"
    production.category = "analyses"
    production.rundir = "/tmp/test_rundir"
    production.status = "wait"
    production.job_id = None

    production.event = MagicMock()
    production.event.name = "GW150914"
    production.event.repository = MagicMock()
    production.event.repository.directory = "/tmp/test_repo"
    production.event.repository.find_prods.return_value = ["TestProduction.ini"]

    production.meta = {
        "event time": 1126259462.4,
        "interferometers": ["H1", "L1"],
        "waveform": {
            "approximant": "IMRPhenomXPHM",
        },
        "likelihood": {
            "minimum frequency": {"H1": 20, "L1": 20},
        },
        "data": {
            "channels": {
                "H1": "H1:GDS-CALIB_STRAIN",
                "L1": "L1:GDS-CALIB_STRAIN",
            },
            "asd": {
                "H1": "/data/H1_asd.txt",
                "L1": "/data/L1_asd.txt",
            },
        },
        "trigger": {
            "mass1": 36,
            "mass2": 29,
            "spin1z": 0.0,
            "spin2z": 0.0,
            "ra": 1.95,
            "dec": -1.27,
            "distance": 440,
        },
        "scheduler": {
            "accounting group": "ligo.dev.o4.cbc.pe.simple_pe",
        },
    }

    production.get_meta = lambda key: production.meta.get(key)

    return production


@pytest.fixture
def mock_config(monkeypatch):
    """Mock the asimov config object."""
    config_values = {
        ("general", "rundir_default"): "/tmp/run",
        ("general", "webroot"): "/tmp/web",
        ("pipelines", "environment"): "/opt/conda",
        ("condor", "user"): "test.user",
    }

    def mock_get(section, key):
        return config_values.get((section, key), "")

    mock_config_module = MagicMock()
    mock_config_module.get = mock_get

    monkeypatch.setattr("asimov_simplepe.simplepe.config", mock_config_module)
    return mock_config_module


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
