"""Observable application state exposed to components via context.

House pattern (Sherlock/KTV): one `@ft.observable` singleton, provided
through `ft.create_context`, read by components with `ft.use_context`.
Components mutate fields directly and bump a `*_version` int when a whole
collection is replaced, so re-renders are explicit rather than relying on
deep diffing large lists.
"""

import flet as ft

from core.state import AppState, state

AppStateCtx = ft.create_context(state)
