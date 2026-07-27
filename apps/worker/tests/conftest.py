"""Test bootstrap. Suppress third-party import-time env noise before any heavy
import (trimesh -> urllib3 warns about LibreSSL on macOS system python). This is
environmental, not a signal about our code.
"""
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*LibreSSL.*")
