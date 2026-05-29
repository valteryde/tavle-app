const SERVICE: &str = "tavle-app";
const ADMIN_TOKEN_USER: &str = "admin_api_token";

pub fn get_admin_token() -> Result<Option<String>, String> {
    let entry = keyring::Entry::new(SERVICE, ADMIN_TOKEN_USER).map_err(|e| e.to_string())?;
    match entry.get_password() {
        Ok(token) if !token.is_empty() => Ok(Some(token)),
        Ok(_) => Ok(None),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

pub fn set_admin_token(token: &str) -> Result<(), String> {
    let entry = keyring::Entry::new(SERVICE, ADMIN_TOKEN_USER).map_err(|e| e.to_string())?;
    entry.set_password(token).map_err(|e| e.to_string())
}

pub fn clear_admin_token() -> Result<(), String> {
    let entry = keyring::Entry::new(SERVICE, ADMIN_TOKEN_USER).map_err(|e| e.to_string())?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
