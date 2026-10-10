//! Every mutation case names a test that exists. A renamed test is caught here, before a mutate run
//! waits on it in CI.

use std::fs;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-testnames-{name}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("scripts/mutations")).unwrap();
    path
}

fn write(path: &Path, text: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
}

fn spec_with_test(repo: &Path, test: &str) {
    let spec = format!(
        r#"[{{"name": "add adds", "file": "toy/calc.py", "old": "a + b", "new": "a - b", "test": "{test}"}}]"#
    );
    write(&repo.join("scripts/mutations/toy.json"), &spec);
    write(
        &repo.join("toy/calc.py"),
        "def add(a, b):\n    return a + b\n",
    );
}

fn misses_for(repo: &Path) -> Vec<String> {
    fwtest::mutate::test_misses(repo).expect("read the mutation specs")
}

#[test]
fn a_python_test_that_is_defined_in_its_file_is_not_a_miss() {
    let repo = scratch("defined");
    spec_with_test(&repo, "toy/test_calc.py::test_add");
    write(
        &repo.join("toy/test_calc.py"),
        "def test_add():\n    pass\n",
    );
    assert!(misses_for(&repo).is_empty());
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_parametrized_id_and_a_class_part_are_ignored_when_looking_for_the_function() {
    let repo = scratch("params");
    spec_with_test(&repo, "toy/test_calc.py::TestCalc::test_add[2-3]");
    write(
        &repo.join("toy/test_calc.py"),
        "class TestCalc:\n    def test_add(self, n):\n        pass\n",
    );
    assert!(misses_for(&repo).is_empty());
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_renamed_python_test_is_a_miss_that_names_the_case_and_the_function() {
    let repo = scratch("renamed");
    spec_with_test(&repo, "toy/test_calc.py::test_add");
    write(
        &repo.join("toy/test_calc.py"),
        "def test_plus():\n    pass\n",
    );
    let misses = misses_for(&repo);
    assert_eq!(misses.len(), 1, "{misses:?}");
    assert!(misses[0].contains("add adds"), "{misses:?}");
    assert!(
        misses[0].contains("has no function test_add in toy/test_calc.py"),
        "{misses:?}"
    );
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_function_whose_name_only_starts_with_the_wanted_one_is_a_miss() {
    let repo = scratch("prefix");
    spec_with_test(&repo, "toy/test_calc.py::test_add");
    write(
        &repo.join("toy/test_calc.py"),
        "def test_add_more():\n    pass\n",
    );
    assert_eq!(misses_for(&repo).len(), 1);
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_test_file_that_does_not_exist_is_a_miss() {
    let repo = scratch("nofile");
    spec_with_test(&repo, "toy/test_gone.py::test_add");
    let misses = misses_for(&repo);
    assert_eq!(misses.len(), 1, "{misses:?}");
    assert!(misses[0].contains("toy/test_gone.py"), "{misses:?}");
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_cargo_test_is_found_in_its_integration_test_file() {
    let repo = scratch("cargo-ok");
    spec_with_test(
        &repo,
        "cargo:flexweek-engine:desk_update:test_checks_the_feed",
    );
    write(
        &repo.join("engine/engine/tests/desk_update.rs"),
        "#[test]\nfn test_checks_the_feed() {}\n",
    );
    assert!(misses_for(&repo).is_empty());
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_renamed_cargo_test_is_a_miss() {
    let repo = scratch("cargo-renamed");
    spec_with_test(
        &repo,
        "cargo:flexweek-engine:desk_update:test_checks_the_feed",
    );
    write(
        &repo.join("engine/engine/tests/desk_update.rs"),
        "#[test]\nfn test_checks_the_feed_again() {}\n",
    );
    let misses = misses_for(&repo);
    assert_eq!(misses.len(), 1, "{misses:?}");
    assert!(
        misses[0].contains("test_checks_the_feed is not a function"),
        "{misses:?}"
    );
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_cargo_test_name_in_the_wrong_target_file_is_a_miss() {
    let repo = scratch("cargo-target");
    spec_with_test(
        &repo,
        "cargo:flexweek-engine:desk_update:test_checks_the_feed",
    );
    write(
        &repo.join("engine/engine/tests/desk_updater_check.rs"),
        "#[test]\nfn test_checks_the_feed() {}\n",
    );
    assert_eq!(misses_for(&repo).len(), 1);
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn a_malformed_cargo_test_is_a_miss() {
    let repo = scratch("cargo-bad");
    spec_with_test(&repo, "cargo:flexweek-engine:desk_update");
    assert_eq!(misses_for(&repo).len(), 1);
    let _ = fs::remove_dir_all(repo);
}

#[test]
fn the_real_mutation_specs_name_tests_that_exist() {
    let checkout = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let misses = fwtest::mutate::test_misses(&checkout).expect("read the mutation specs");
    assert!(
        misses.is_empty(),
        "mutation cases whose test does not exist:\n{}",
        misses.join("\n")
    );
}
