use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_autostart::MacosLauncher;
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

// Holds the running backend sidecar's handle so it can be killed on app
// exit -- the sidecar has its own lifetime independent of the webview
// window, and PyInstaller-bundled processes don't die with their parent
// on their own.
struct BackendProcess(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_autostart::init(
      MacosLauncher::LaunchAgent,
      None,
    ))
    .manage(BackendProcess(Mutex::new(None)))
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // launch-on-login, per docs/build-plan.md Phase 6 -- champ select
      // gives ~30s, so the backend (and its pgserver + model-load startup
      // cost) needs to already be warm before a game starts, not launched
      // fresh the first time the user opens the app mid-lobby.
      let autostart = app.autolaunch();
      if !autostart.is_enabled().unwrap_or(false) {
        let _ = autostart.enable();
      }

      let (_rx, child) = app
        .shell()
        .sidecar("lol-matchbook-backend")
        .expect("failed to resolve the backend sidecar binary")
        .spawn()
        .expect("failed to spawn the backend sidecar");

      *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(|app_handle, event| {
      // RunEvent::Exit, not WindowEvent::Destroyed -- a real test here
      // (killing the app process directly, simulating a force-quit)
      // showed Destroyed only fires on a graceful window close, leaving
      // the sidecar orphaned on process-level termination. Exit fires
      // for both a real app quit and the window closing, so this is the
      // one place that reliably catches both.
      if let tauri::RunEvent::Exit = event {
        if let Some(child) = app_handle
          .state::<BackendProcess>()
          .0
          .lock()
          .unwrap()
          .take()
        {
          let _ = child.kill();
        }
      }
    });
}
