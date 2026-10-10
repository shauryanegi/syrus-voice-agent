"""Unit tests never load private local environment files."""

import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
