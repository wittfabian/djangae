# This file starts up VSCode remote debugging if the ptvsd package is available

import logging
import os

_DEBUGGER_PORT = 8099
_ENABLE_ENV_VAR = "DJANGAE_PTVSD"


def enable():
    if os.environ.get(_ENABLE_ENV_VAR):
        try:
            import ptvsd
            ptvsd.enable_attach(secret='djangae', address=('0.0.0.0', _DEBUGGER_PORT))
            logging.critical("Remote debugging enabled. Attach debugger now.")
            return True
        except ImportError:
            logging.critical("Remote debugging disabled, install ptvsd if required")
            return False

