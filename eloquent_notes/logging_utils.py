import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def get_log_dir() -> str:
    xdg_state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(xdg_state, "eloquent-notes")

def setup_logging(log_level_str: str = "INFO") -> logging.Logger:
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    logger = logging.getLogger("eloquent_notes")
    logger.setLevel(level)
    
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] (%(threadName)s) %(name)s.%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "app.log")
        
        file_handler = RotatingFileHandler(
            log_file_path, 
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not initialize file logging: {e}", file=sys.stderr)

    return logger
