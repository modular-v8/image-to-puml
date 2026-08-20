"""Shared skip marker for tests that shell out to the real render
toolchain (java + dot + plantuml.jar), not just java.

T5.7: every one of these tests previously defined its own
`shutil.which("java") is None` skip condition, duplicated six times.
That check is insufficient on its own -- GitHub's ubuntu-latest and
windows-latest runners both ship a JRE by default but not Graphviz, so
`@requires_java`-only tests ran for real on CI instead of skipping, and
failed on the missing `dot` (and, on any machine, `tools/plantuml.jar`
is a separately-fetched file that is gitignored and not guaranteed
present just because java+dot are). Using the real `preflight()` check
-- the same one `doctor`/rendering itself uses -- means the skip
condition can never drift from what actually makes rendering work.
"""

from __future__ import annotations

import pytest

from umlregen.errors import DependencyMissing
from umlregen.render.plantuml import preflight


def _render_toolchain_available() -> bool:
    try:
        preflight()
    except DependencyMissing:
        return False
    return True


requires_render_toolchain = pytest.mark.skipif(
    not _render_toolchain_available(),
    reason="java, dot, and plantuml.jar must all be available to actually render",
)
