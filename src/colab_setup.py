import subprocess
import sys

from src.common.logging import console


def _is_colab() -> bool:
    try:
        import google.colab  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def install_system_deps() -> None:
    """Install poppler-utils and graphviz. No-op with a notice when not in Colab."""
    if _is_colab():
        subprocess.run(["apt-get", "install", "-y", "poppler-utils", "graphviz"], check=True)
    else:
        console.print("[yellow]install_system_deps: not in Colab — ensure poppler-utils and graphviz are installed locally.[/yellow]")


def install_python_deps() -> None:
    """Install Python dependencies from requirements.txt."""
    from src.common.paths import ROOT
    req = ROOT / "requirements.txt"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], check=True)
