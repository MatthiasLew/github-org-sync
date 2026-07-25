# github-org-sync package
try:
    from importlib.metadata import version

    __version__ = version("github-org-sync")
except Exception:
    __version__ = "1.3.1"
