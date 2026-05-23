from pathlib import Path


_package_dir = Path(__file__).resolve().parents[2] / "my"
__path__ = [str(_package_dir)]