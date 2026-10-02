use flexweek_engine::snapshot::{
    format_recovery_code, hash_recovery_code, normalize_recovery_code,
};

const CODE: &str = "a1b2-c3d4-e5f6-7890";

fn recovery_code_matches(presented: &str, stored_hash: &str) -> bool {
    hash_recovery_code(presented) == stored_hash
}

fn hyphenated_hex(code: &str) -> bool {
    let parts: Vec<&str> = code.split('-').collect();
    parts.len() == 4
        && parts.iter().all(|part| {
            part.len() == 4
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        })
}

#[test]
fn test_normalize_strips_hyphens_and_case() {
    assert_eq!(
        normalize_recovery_code("A1B2-C3D4-E5F6-7890"),
        "a1b2c3d4e5f67890"
    );
    assert_eq!(
        normalize_recovery_code("a1b2c3d4e5f67890"),
        "a1b2c3d4e5f67890"
    );
}

#[test]
fn test_same_code_hashes_equal_with_or_without_hyphens() {
    assert_eq!(
        hash_recovery_code(CODE),
        hash_recovery_code("A1B2C3D4E5F67890")
    );
    assert_ne!(
        hash_recovery_code(CODE),
        hash_recovery_code("a1b2-c3d4-e5f6-7891")
    );
    assert!(recovery_code_matches(
        "A1B2-C3D4-E5F6-7890",
        &hash_recovery_code(CODE)
    ));
    assert!(!recovery_code_matches(
        "a1b2-c3d4-e5f6-7891",
        &hash_recovery_code(CODE)
    ));
}

#[test]
fn test_generated_codes_are_eight_unique_hyphenated_hex_strings() {
    // The wrapper draws these with secrets.token_hex(8). The engine only formats them.
    let raw = [
        "a1b2c3d4e5f67890",
        "0011223344556677",
        "89abcdef01234567",
        "fedcba9876543210",
        "0123456789abcdef",
        "aaaabbbbccccdddd",
        "1234567890abcdef",
        "deadbeefcafebabe",
    ];
    let codes: Vec<String> = raw.iter().copied().map(format_recovery_code).collect();
    assert_eq!(codes.len(), 8);
    assert_eq!(
        codes
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        8
    );
    assert!(codes.iter().all(|code| hyphenated_hex(code)));
    assert!(codes.iter().all(|code| hash_recovery_code(code) != *code));
}
