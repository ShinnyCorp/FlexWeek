//! Every case in scripts/mutations matches its source exactly once.
//! A later move of a rule into Rust fails here before a mutate run.

use std::path::PathBuf;

#[test]
fn every_mutation_pattern_matches_once() {
    let checkout = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let misses = fwtest::mutate::pattern_misses(&checkout).expect("read the mutation specs");
    assert!(
        misses.is_empty(),
        "mutation patterns that do not match once:\n{}",
        misses.join("\n")
    );
}
