use std::io::{self, Read};

fn main() {
    let result = (|| -> Result<serde_json::Value, String> {
        let path = std::env::args()
            .nth(1)
            .ok_or("usage: hct-core <database>")?;
        let mut input = String::new();
        io::stdin()
            .take(1_048_577)
            .read_to_string(&mut input)
            .map_err(|e| e.to_string())?;
        if input.len() > 1_048_576 {
            return Err("请求过大".into());
        }
        hct_core::dispatch(
            &path,
            serde_json::from_str(&input).map_err(|e| e.to_string())?,
        )
    })();
    match result {
        Ok(value) => println!("{}", value),
        Err(error) => {
            println!("{}", serde_json::json!({"error":error}));
            std::process::exit(1);
        }
    }
}
