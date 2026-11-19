use anyhow::{Context, Result};
use serde::Deserialize;
use std::{
    env, fs,
    path::{Path, PathBuf},
};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Package {
    layout_version: u32,
    version: String,
    target: String,
    entrypoint: String,
}

fn executable(path: &Path) -> Result<PathBuf> {
    let path = path
        .canonicalize()
        .context("selected Codex binary is missing; set CODEX_BINARY to an installed executable")?;
    let metadata = fs::metadata(&path)?;
    anyhow::ensure!(metadata.is_file(), "selected Codex binary must be a file");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        anyhow::ensure!(
            metadata.permissions().mode() & 0o111 != 0,
            "selected Codex binary is not executable"
        );
    }
    Ok(path)
}

/// Select the explicit binary or the installer's active release, without scanning releases.
pub fn resolve(home: &Path) -> Result<PathBuf> {
    select(
        home,
        env::var_os("CODEX_BINARY").map(PathBuf::from).as_deref(),
    )
}
fn select(home: &Path, explicit: Option<&Path>) -> Result<PathBuf> {
    if let Some(path) = explicit {
        return executable(path);
    }
    let root = home.join("packages/app-server-daemon");
    let current = root.join("current");
    anyhow::ensure!(
        fs::symlink_metadata(&current).is_ok_and(|value| value.file_type().is_symlink()),
        "active installed Codex pointer is missing or invalid; install Codex or set CODEX_BINARY explicitly"
    );
    let release = current
        .canonicalize()
        .context("active installed Codex release is missing; set CODEX_BINARY explicitly")?;
    let releases = root
        .join("releases")
        .canonicalize()
        .context("installed Codex releases directory is missing")?;
    anyhow::ensure!(
        release.parent() == Some(releases.as_path()),
        "active Codex pointer must select one installed release"
    );
    let manifest = release.join("codex-package.json");
    anyhow::ensure!(
        fs::metadata(&manifest)
            .context("active Codex package manifest is missing")?
            .len()
            <= 65536,
        "Codex package manifest exceeds limit"
    );
    let package: Package = serde_json::from_slice(&fs::read(manifest)?)
        .context("active Codex package manifest is invalid")?;
    let version_valid = package.version.len() <= 32
        && package.version.split('.').count() == 3
        && package
            .version
            .split('.')
            .all(|part| !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit()));
    let target_valid = !package.target.is_empty()
        && package.target.len() <= 64
        && package
            .target
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-');
    anyhow::ensure!(
        package.layout_version == 1
            && package.entrypoint == "bin/codex"
            && version_valid
            && target_valid
            && release.file_name().and_then(|name| name.to_str())
                == Some(format!("{}-{}", package.version, package.target).as_str()),
        "active Codex package manifest does not match its selected release"
    );
    let binary = executable(&release.join(&package.entrypoint))?;
    anyhow::ensure!(
        binary.starts_with(&release),
        "active Codex executable escapes its selected release"
    );
    Ok(binary)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::{fs::PermissionsExt, fs::symlink};
    fn fixture() -> (tempfile::TempDir, PathBuf) {
        let home = tempfile::tempdir().unwrap();
        let root = home.path().join("packages/app-server-daemon");
        let release = root.join("releases/0.170.0-aarch64-apple-darwin");
        fs::create_dir_all(release.join("bin")).unwrap();
        fs::write(release.join("bin/codex"), "#!/bin/sh\nexit 0\n").unwrap();
        fs::set_permissions(release.join("bin/codex"), fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(release.join("codex-package.json"), r#"{"layoutVersion":1,"version":"0.170.0","target":"aarch64-apple-darwin","entrypoint":"bin/codex"}"#).unwrap();
        symlink(&release, root.join("current")).unwrap();
        (home, release.canonicalize().unwrap())
    }
    #[test]
    fn selects_only_current_release_and_explicit_override_wins() {
        let (home, release) = fixture();
        assert_eq!(
            select(home.path(), None).unwrap(),
            release.join("bin/codex")
        );
        fs::create_dir_all(
            home.path()
                .join("packages/app-server-daemon/releases/99.0.0-other"),
        )
        .unwrap();
        assert_eq!(
            select(home.path(), None).unwrap(),
            release.join("bin/codex")
        );
        let empty = tempfile::tempdir().unwrap();
        assert_eq!(
            select(empty.path(), Some(&release.join("bin/codex"))).unwrap(),
            release.join("bin/codex")
        );
        assert!(select(home.path(), Some(Path::new("/missing/explicit-codex"))).is_err());
    }
    #[test]
    fn rejects_missing_pointer_manifest_and_executable() {
        let empty = tempfile::tempdir().unwrap();
        assert!(select(empty.path(), None).is_err());
        let (home, release) = fixture();
        fs::remove_file(release.join("codex-package.json")).unwrap();
        assert!(select(home.path(), None).is_err());
        let (home, release) = fixture();
        fs::set_permissions(release.join("bin/codex"), fs::Permissions::from_mode(0o600)).unwrap();
        assert!(select(home.path(), None).is_err());
    }
    #[test]
    fn rejects_invalid_manifest_pointer_and_escaped_executable() {
        let (home, release) = fixture();
        fs::write(release.join("codex-package.json"),r#"{"layoutVersion":1,"version":"0.169.1","target":"aarch64-apple-darwin","entrypoint":"../codex"}"#).unwrap();
        assert!(select(home.path(), None).is_err());
        let (home, release) = fixture();
        let root = home.path().join("packages/app-server-daemon");
        fs::remove_file(root.join("current")).unwrap();
        symlink(home.path(), root.join("current")).unwrap();
        assert!(select(home.path(), None).is_err());
        fs::remove_file(root.join("current")).unwrap();
        symlink(&release, root.join("current")).unwrap();
        let outside = home.path().join("outside");
        fs::write(&outside, "executable").unwrap();
        fs::set_permissions(&outside, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_file(release.join("bin/codex")).unwrap();
        symlink(outside, release.join("bin/codex")).unwrap();
        assert!(select(home.path(), None).is_err());
    }
}
