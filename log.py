import logging
import inspect
from pprint import pformat as ppr
logging.basicConfig(level=logging.DEBUG)

class CustomFormatter(logging.Formatter):
    green = "\033[1;92m"
    yellow = "\033[1;93m"
    red = "\033[1;31m"
    blue = "\033[1;94m"
    reset = "\033[0m"
    format = "%(asctime)s - %(levelname)s\t- %(name)s - %(message)s "

    FORMATS = {
        logging.DEBUG: blue + format + reset,
        logging.INFO: green + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    # Prevent passing events to the handlers of higher severity
    logger.propagate = False
    # Set formatter for the logger.
    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    logger.addHandler(handler)
    return logger

def debug(logger, variable, **kwargs):
    s = ""
    callers_local_vars = inspect.currentframe().f_back.f_locals.items()
    for var_name, var_val in callers_local_vars:
        if var_val is variable:
            s += f"{var_name}="
    s += ppr(variable, width=500, **kwargs)
    logger.debug(s)