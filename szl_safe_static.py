# SPDX-License-Identifier: Apache-2.0
"""Root-confined static-file lookup for application catch-all routes."""
from __future__ import annotations

from os import PathLike
from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class RootedStaticFiles:
    """Serve a relative URL path through Starlette's containment-checked API.

    Starlette's ``StaticFiles.lookup_path`` canonicalizes the configured root
    and candidate then requires ``os.path.commonpath`` containment.  This thin
    adapter exposes a nullable response so SPA routes can fall back to their
    index without ever constructing a filesystem path from request data.
    """

    def __init__(self, directory: str | PathLike[str]) -> None:
        self._files = StaticFiles(directory=str(directory), check_dir=False)

    async def get(self, relative_path: str, scope: dict[str, Any]) -> Response | None:
        if not isinstance(relative_path, str):
            return None
        try:
            response = await self._files.get_response(relative_path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return None
            raise
        except ValueError:
            # ``os.path.commonpath`` rejects mixed-drive Windows paths. Treat
            # that attacker-controlled shape as an ordinary miss, never a 500.
            return None
        return None if response.status_code == 404 else response


__all__ = ["RootedStaticFiles"]
