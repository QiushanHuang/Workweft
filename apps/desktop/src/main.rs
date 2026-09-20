use std::{
    net::{TcpListener, TcpStream},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::Manager;

struct Service(Mutex<Option<Child>>);

fn main() {
    let app=tauri::Builder::default()
        .setup(|app| {
            let resources=app.path().resource_dir()?;
            let bundled=resources.join("workspace");
            let root=if bundled.join("apps/workbench/server.py").exists(){bundled}else{std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap().to_path_buf()};
            let data=app.path().app_data_dir()?;
            std::fs::create_dir_all(&data)?;
            let database=std::env::var_os("HCT_DATABASE").map(std::path::PathBuf::from).unwrap_or_else(||data.join("workbench.sqlite3"));
            let socket=TcpListener::bind("127.0.0.1:0")?;
            let port=socket.local_addr()?.port(); drop(socket);
            let python=std::env::var("HCT_PYTHON").unwrap_or_else(|_|"/usr/bin/python3".into());
            let log=std::fs::OpenOptions::new().create(true).append(true).open(data.join("service.log"))?;
            let mut child=Command::new(python).arg(root.join("apps/workbench/server.py"))
                .env("HCT_PORT",port.to_string()).env("HCT_DATABASE",database)
                .env("PYTHONDONTWRITEBYTECODE","1").stdout(Stdio::from(log.try_clone()?)).stderr(Stdio::from(log)).spawn()?;
            let mut ready=false;
            for _ in 0..100 {
                if child.try_wait()?.is_some(){break;}
                if TcpStream::connect(("127.0.0.1",port)).is_ok(){ready=true;break;}
                std::thread::sleep(Duration::from_millis(50));
            }
            if !ready {let _=child.kill();let _=child.wait();return Err("本地服务启动失败，请检查 Application Support/local.harness.control/service.log".into());}
            app.manage(Service(Mutex::new(Some(child))));
            tauri::WebviewWindowBuilder::new(app,"main",tauri::WebviewUrl::External(format!("http://127.0.0.1:{port}/").parse()?))
                .title("Workweft").inner_size(1280.0,850.0).min_inner_size(820.0,600.0).build()?;
            Ok(())
        }).build(tauri::generate_context!()).expect("无法启动 Workweft");
    app.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(service) = app.try_state::<Service>() {
                if let Some(mut child) = service.0.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
