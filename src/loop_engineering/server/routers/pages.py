"""Page routes router.

Note: Full page routes are currently defined in app.py for backward compatibility.
This module serves as the extraction target for future route migration.
"""

# Page routes are defined directly in app.py using @app.get() decorators.
# Migration path: move each @app.get() to @router.get() here, then
# in app.py replace with app.include_router(pages_router).
