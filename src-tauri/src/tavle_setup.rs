use crate::secrets;

/// Fetch the admin API token from Tavle's setup page (triggers token generation on server).
pub fn fetch_setup_token(base_url: &str) -> Result<String, String> {
    let url = format!("{}/setup", base_url.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::limited(5))
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let response = client
        .get(&url)
        .send()
        .map_err(|e| format!("Could not reach Tavle at {url}: {e}"))?;

    if !response.status().is_success() {
        return Err(format!(
            "Tavle setup page returned {}. Is the server running?",
            response.status()
        ));
    }

    let html = response.text().map_err(|e| e.to_string())?;

    parse_token_from_setup_html(&html).ok_or_else(|| {
        "Could not read admin token from Tavle setup page. Setup may already be complete.".into()
    })
}

fn parse_token_from_setup_html(html: &str) -> Option<String> {
    // Rendered setup.html: <input type="text" id="apiToken" value="TOKEN" readonly
    if let Some(start) = html.find(r#"id="apiToken""#) {
        let slice = &html[start..];
        if let Some(value_idx) = slice.find("value=\"") {
            let rest = &slice[value_idx + 7..];
            if let Some(end) = rest.find('"') {
                let token = rest[..end].trim();
                if !token.is_empty() && token != "{{ admin_token }}" {
                    return Some(token.to_string());
                }
            }
        }
    }
    None
}

/// Mark Tavle setup complete and store the admin token in the OS keychain.
pub fn complete_tavle_setup(base_url: &str, token: &str) -> Result<(), String> {
    let url = format!("{}/setup/complete", base_url.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::limited(5))
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let response = client
        .post(&url)
        .send()
        .map_err(|e| format!("Failed to complete Tavle setup: {e}"))?;

    if !response.status().is_success() && !response.status().is_redirection() {
        return Err(format!(
            "Tavle setup completion failed with status {}",
            response.status()
        ));
    }

    secrets::set_admin_token(token)?;
    Ok(())
}
