"""Re-export the upstream SQLAlchemy dialect compliance suite.

Importing the suite here makes its hundreds of dialect-conformance tests
discoverable under ``compliance/``. This directory is **not** part of the
default ``test/*test_*.py`` glob in ``setup.cfg``; it is run explicitly by
``.github/workflows/compliance.yml`` so the always-green smoke suite under
``test/`` stays fast and merge-gating, and the compliance suite stays
advisory until ``requirements.py`` has been tuned off measured behaviour.
"""

from sqlalchemy.testing.suite import *  # noqa: F401,F403
