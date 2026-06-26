"""HTMX fragment routes router.

Note: HTMX fragment routes are currently defined in app.py for backward compatibility.
This module serves as the extraction target for future route migration.
"""

# Fragment routes are defined directly in app.py using @app.get() decorators.
# Migration path: move each fragment endpoint to @router.get() here, then
# in app.py replace with app.include_router(fragments_router).
