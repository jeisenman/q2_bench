use anyhow::{Context, Result};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::{
    io::Read,
    process::{Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
const LIMIT: u64 = 2 * 1024 * 1024;

pub struct Output {
    pub success: bool,
    pub stdout: Vec<u8>,
    pub timed_out: bool,
}

/// Run one child with bounded output and a deadline. Discard private stderr.
pub fn execute(command: &mut Command, deadline: Instant, own_group: bool) -> Result<Output> {
    anyhow::ensure!(Instant::now() < deadline, "execution deadline expired");
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(unix)]
    if own_group {
        command.process_group(0);
    }
    let mut child = command
        .spawn()
        .context("cannot start configured executable")?;
    let stdout = child.stdout.take().context("missing stdout")?;
    let stderr = child.stderr.take().context("missing stderr")?;
    let exceeded = Arc::new(AtomicBool::new(false));
    let read = |stream: Box<dyn Read + Send>| {
        let exceeded = exceeded.clone();
        thread::spawn(move || {
            let mut bytes = Vec::new();
            stream.take(LIMIT + 1).read_to_end(&mut bytes)?;
            if bytes.len() > LIMIT as usize {
                exceeded.store(true, Ordering::Relaxed);
            }
            Ok::<_, std::io::Error>(bytes)
        })
    };
    let out = read(Box::new(stdout));
    let err = read(Box::new(stderr));
    let mut timed_out = false;
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline || exceeded.load(Ordering::Relaxed) {
            // A full output reader stops at its cap. Stop the entire child group.
            if Instant::now() >= deadline {
                timed_out = true;
            }
            #[cfg(unix)]
            unsafe {
                if own_group {
                    libc::kill(-(child.id() as i32), libc::SIGKILL);
                }
            }
            let _ = child.kill();
            break child.wait()?;
        }
        thread::sleep(Duration::from_millis(10));
    };
    #[cfg(unix)]
    unsafe {
        if own_group {
            libc::kill(-(child.id() as i32), libc::SIGKILL);
        }
    }
    let stdout = out
        .join()
        .map_err(|_| anyhow::anyhow!("stdout reader failed"))??;
    let stderr = err
        .join()
        .map_err(|_| anyhow::anyhow!("stderr reader failed"))??;
    anyhow::ensure!(
        stdout.len() <= LIMIT as usize && stderr.len() <= LIMIT as usize,
        "child output exceeds limit"
    );
    Ok(Output {
        success: status.success(),
        stdout,
        timed_out,
    })
}
