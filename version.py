"""Central version identifier for Mesh.

Bump this on every release. Every part of the app (the startup banner,
the /status and /version commands, and the MCP client handshake) reads
from this single constant so the version never drifts out of sync.
"""

__version__ = "1.0.0"
