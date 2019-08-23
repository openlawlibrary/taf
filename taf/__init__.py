import os
from pathlib import Path

# Add ykpers to path
if 'ykpers' not in os.environ['PATH']:
  ykpers_bin_path = Path(__file__).parent.parent / 'ykpers' / 'bin'
  if not ykpers_bin_path.exists():
    raise Exception('ykpers is not set in PATH, neither downloaded.')
  os.environ['PATH'] += os.pathsep + str(ykpers_bin_path.resolve())
