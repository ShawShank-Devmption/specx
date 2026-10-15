"""Shared sandbox boundary for safety experiments and evaluation.

Use SandboxClient as a context manager to release HTTP resources. close(session_id)
destroys a session; FakeSandbox supports the supplied shop fixtures only.
"""

from specx.client.fake import FakeSandbox
from specx.client.sandbox import SandboxClient, SandboxError

__all__ = ["FakeSandbox", "SandboxClient", "SandboxError"]
