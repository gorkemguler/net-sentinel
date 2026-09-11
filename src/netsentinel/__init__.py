"""NetSentinel - distributed home-network security monitor.

The project is split into two runtimes that talk to each other over an
authenticated HTTP API:

* ``netsentinel.hub``    - the aggregator: REST API, dashboard, alerting, storage.
* ``netsentinel.sensor`` - the probe: device discovery, passive DNS, port-change scans.

A single Raspberry Pi can run both, but the design target is one Pi per role.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
