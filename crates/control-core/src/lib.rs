pub mod domain;
pub mod review;
mod storage;

use serde_json::Value;

/// Versioned JSON boundary shared by the CLI and the local workbench.
pub fn dispatch(path: &str, request: Value) -> Result<Value, String> {
    storage::dispatch(path, request)
}
