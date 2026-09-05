"""Version of the dlss5ve package and of the upstream application it wraps.

``__version__`` follows the upstream release in its first two components and
counts CLI/engine revisions on top of that release in the third (7.0.0 is the
first package built on DLSS 5 Visual Enhancer v7.0). Bump the third component
for changes on this branch; reset it to 0 when a new upstream release is
merged. ``APP_VERSION`` is the upstream version string shown in its About tab.
"""

__version__ = "7.0.0"
APP_VERSION = "v7.0"
