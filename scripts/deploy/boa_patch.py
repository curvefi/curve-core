"""
Monkey patch for boa.load and boa.load_partial to inject compiler arguments.
This ensures all contracts are compiled with the EVM version from chain settings.
"""
import boa

from scripts.logging_config import get_logger
from settings.models import ChainConfig

logger = get_logger()

# Store the original load_partial and load functions
_original_load_partial = boa.load_partial
_original_load = boa.load

# Global variable to store current chain settings
_current_chain_settings = None
_chain_settings_initialized = False


def set_chain_settings(chain_settings: ChainConfig):
    """Set the current chain settings for compiler args. Can only be called once."""
    global _current_chain_settings, _chain_settings_initialized
    
    if _chain_settings_initialized:
        raise RuntimeError("Chain settings have already been initialized. Cannot set them again.")
    
    _current_chain_settings = chain_settings
    _chain_settings_initialized = True
    logger.info(f"Chain settings initialized with EVM version: {chain_settings.evm_version}")


def _inject_compiler_args(kwargs):
    """Inject compiler args into kwargs if not already present."""
    if _chain_settings_initialized and "compiler_args" not in kwargs:
        kwargs["compiler_args"] = {"evm_version": _current_chain_settings.evm_version}
    elif not _chain_settings_initialized and "compiler_args" not in kwargs:
        # Default to shanghai for standalone scripts
        kwargs["compiler_args"] = {"evm_version": "shanghai"}
        logger.warning("Chain settings not initialized. Using default EVM version: shanghai")


def load_partial_wrapper(*args, **kwargs):
    """Wrapper for boa.load_partial that includes compiler args from chain settings."""
    _inject_compiler_args(kwargs)
    return _original_load_partial(*args, **kwargs)


def load_wrapper(*args, **kwargs):
    """Wrapper for boa.load that includes compiler args from chain settings."""
    _inject_compiler_args(kwargs)
    return _original_load(*args, **kwargs)


# Apply the monkey patches
def apply_patches():
    """Apply the monkey patches to boa.load and boa.load_partial."""
    boa.load_partial = load_partial_wrapper
    boa.load = load_wrapper
    logger.debug("Boa patches applied")


# Apply patches on import
apply_patches()