import sys
import os
# Ensure src/ is on sys.path so modules using unqualified imports (e.g., 'import config') work
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC_DIR = os.path.join(ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
