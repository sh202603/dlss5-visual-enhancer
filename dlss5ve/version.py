"""Version of the dlss5ve package and of the upstream application it wraps.

``__version__`` follows the upstream release in its first two components and
counts CLI/engine revisions on top of that release in the third (11.0.0 is the
first package built on Visual Enhancer v11.0; the app was called DLSS 5 Visual
Enhancer up to v9). Bump the third component for changes on this branch; reset
it to 0 when a new upstream release is merged. ``APP_VERSION`` is the upstream
release string; the About view of the app shortens it to "v11".
"""

__version__ = "11.0.0"
APP_VERSION = "v11.0"
