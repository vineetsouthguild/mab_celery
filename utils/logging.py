import time
import functools
import logging
from contextlib import contextmanager

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_logger(name=None):
    """
    Get a logger with the specified name or the calling module's name.
    This helps maintain consistent logging across the application.
    """
    if name is None:
        # Get the name of the module that called this function
        import inspect
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else __name__
    
    return logging.getLogger(name)

def timing_decorator(func=None, *, level="INFO", log_args=False):
    """
    Decorator that logs the execution time of a function
    
    Args:
        func: The function to decorate
        level: Log level ("DEBUG", "INFO", "WARNING", "ERROR")
        log_args: Whether to log function arguments
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Get logger from the module where the decorated function is defined
            fn_logger = logging.getLogger(fn.__module__)
            log_method = getattr(fn_logger, level.lower())
            
            # Log function call with arguments if required
            if log_args:
                arg_str = ', '.join([str(arg) for arg in args])
                kwarg_str = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
                all_args = ', '.join(filter(None, [arg_str, kwarg_str]))
                log_method(f"Calling {fn.__name__}({all_args})")
            
            start_time = time.time()
            result = fn(*args, **kwargs)
            end_time = time.time()
            
            log_method(f"{fn.__name__} executed in {end_time - start_time:.4f} seconds")
            return result
        return wrapper
    
    # This allows the decorator to be used with or without arguments
    if func is not None:
        return decorator(func)
    return decorator

@contextmanager
def timer(name, level="INFO", logger_name=None):
    """
    Context manager for timing code blocks
    
    Args:
        name: Name of the operation being timed
        level: Log level ("DEBUG", "INFO", "WARNING", "ERROR")
        logger_name: Name of the logger to use (None for module-based logger)
    
    Example:
        with timer("Processing file"):
            # code to time
    """
    timer_logger = get_logger(logger_name)
    log_method = getattr(timer_logger, level.lower())
    
    start_time = time.time()
    try:
        yield
    finally:
        end_time = time.time()
        log_method(f"{name} completed in {end_time - start_time:.4f} seconds")
