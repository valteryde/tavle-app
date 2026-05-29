"""
First-run setup management for the Collaborative Whiteboard.
Handles initial configuration and API key generation.
Stores configuration in the database for persistence across restarts.
"""
import os
import secrets
import logging

logger = logging.getLogger(__name__)

# Setting keys
SETTING_ADMIN_TOKEN = 'admin_api_token'
SETTING_SECRET_KEY = 'secret_key'
SETTING_SETUP_COMPLETE = 'setup_complete'


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def generate_secret_key() -> str:
    """Generate a secure Flask secret key."""
    return secrets.token_hex(32)


def _get_settings_model():
    """
    Lazy import of Settings model to avoid circular imports.
    Returns the Settings model class.
    """
    from models import Settings, db
    
    # Ensure database is connected and tables exist
    if db.is_closed():
        db.connect(reuse_if_open=True)
    
    # Create tables if they don't exist (safe=True means IF NOT EXISTS)
    db.create_tables([Settings], safe=True)
    
    return Settings


def is_setup_complete() -> bool:
    """Check if first-run setup has been completed (from database)."""
    try:
        Settings = _get_settings_model()
        return Settings.get_value(SETTING_SETUP_COMPLETE) == 'true'
    except Exception as e:
        logger.debug(f"Setup check failed (db may not exist yet): {e}")
        return False


def get_db_config(key: str) -> str:
    """Get a configuration value from the database."""
    try:
        Settings = _get_settings_model()
        return Settings.get_value(key)
    except Exception as e:
        logger.debug(f"Failed to get config {key}: {e}")
        return None


def save_db_config(key: str, value: str) -> bool:
    """Save a configuration value to the database."""
    try:
        Settings = _get_settings_model()
        Settings.set_value(key, value)
        return True
    except Exception as e:
        logger.error(f"Failed to save config {key}: {e}")
        return False


def get_or_create_admin_token() -> str:
    """
    Get the admin token, or generate and save one if it doesn't exist.
    Does NOT mark setup as complete - that must be done explicitly.
    """
    # Check if token already exists in database
    existing_token = get_db_config(SETTING_ADMIN_TOKEN)
    if existing_token:
        return existing_token
    
    # Generate new token and save it
    new_token = generate_api_key()
    save_db_config(SETTING_ADMIN_TOKEN, new_token)
    
    # Also generate and save secret key if not exists
    if not get_db_config(SETTING_SECRET_KEY):
        save_db_config(SETTING_SECRET_KEY, generate_secret_key())
    
    logger.info("Generated new admin token (setup not yet complete)")
    return new_token


def mark_setup_complete() -> bool:
    """
    Mark the setup as complete in the database.
    Called when the user confirms they have saved their token.
    """
    success = save_db_config(SETTING_SETUP_COMPLETE, 'true')
    if success:
        logger.info("Setup marked as complete by user")
    return success


def complete_setup(admin_token: str = None) -> dict:
    """
    Complete the first-run setup.
    Generates and saves API keys to the database.
    Returns the configuration.
    """
    config = {
        'setup_complete': True,
        'admin_api_token': admin_token or generate_api_key(),
        'secret_key': generate_secret_key(),
    }
    
    # Save to database
    save_db_config(SETTING_ADMIN_TOKEN, config['admin_api_token'])
    save_db_config(SETTING_SECRET_KEY, config['secret_key'])
    save_db_config(SETTING_SETUP_COMPLETE, 'true')
    
    logger.info("First-run setup completed successfully (saved to database)")
    return config


def get_admin_token() -> str:
    """
    Get the admin API token.
    Priority: Environment variable > Database > Dev default
    """
    # 1. Check environment variable first (production override)
    env_token = os.environ.get('ADMIN_API_TOKEN')
    if env_token and env_token != 'dev-admin-token-change-in-production':
        return env_token
    
    # 2. Check database
    db_token = get_db_config(SETTING_ADMIN_TOKEN)
    if db_token:
        return db_token
    
    # 3. Return dev default (will trigger setup screen)
    return 'dev-admin-token-change-in-production'


def get_secret_key() -> str:
    """
    Get the Flask secret key.
    Priority: Environment variable > Database > Auto-generate
    
    The secret key is automatically generated on first run and stored
    in the database, so users don't need to configure it manually.
    Environment variable override is available for multi-instance deployments.
    """
    # 1. Check environment variable first (for multi-instance deployments)
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    
    # 2. Check database
    db_key = get_db_config(SETTING_SECRET_KEY)
    if db_key:
        return db_key
    
    # 3. Auto-generate and save to database (first run)
    new_key = generate_secret_key()
    if save_db_config(SETTING_SECRET_KEY, new_key):
        logger.info("Generated and saved new secret key to database")
        return new_key
    
    # 4. Fallback: generate but don't persist (database not ready)
    # This is safe as Flask will still work, just sessions won't persist across restarts
    logger.warning("Could not save secret key to database - using ephemeral key")
    return new_key


def needs_setup() -> bool:
    """
    Check if setup is needed.
    Setup is needed if:
    - No environment variables are set for API token AND
    - No token exists in the database
    """
    # If env vars are set, no setup needed
    env_token = os.environ.get('ADMIN_API_TOKEN', '')
    if env_token and env_token != 'dev-admin-token-change-in-production':
        return False
    
    # If setup is complete in database, no setup needed
    if is_setup_complete():
        return False
    
    return True
