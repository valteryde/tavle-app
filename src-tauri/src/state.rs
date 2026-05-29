use std::path::PathBuf;
use std::process::Child;
use std::sync::Mutex;

pub struct TavleProcessState {
    pub child: Mutex<Option<Child>>,
    pub port: Mutex<u16>,
    pub base_url: Mutex<String>,
}

pub struct AppPaths {
    pub app_data_dir: PathBuf,
    pub tavle_data_dir: PathBuf,
    pub metadata_db: PathBuf,
    pub vendor_tavle_dir: PathBuf,
}
