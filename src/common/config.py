import getpass
import os


def get_secret(name: str) -> str:
    """Resolve a secret from Colab userdata → env → .env → interactive prompt."""
    # 1. Google Colab userdata
    try:
        from google.colab import userdata  # type: ignore
        value = userdata.get(name)
        if value:
            return value
    except Exception:
        pass

    # 2. Already in environment
    value = os.environ.get(name)
    if value:
        return value

    # 3. .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        value = os.environ.get(name)
        if value:
            return value
    except ImportError:
        pass

    # 4. Interactive fallback
    return getpass.getpass(f"{name}: ")
