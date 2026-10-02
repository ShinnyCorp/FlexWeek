use flexweek_engine::snapshot::{
    MAX_BODY, transfer_apply_bytes, transfer_apply_envelope, transfer_fits,
};
use serde_json::json;

#[test]
fn test_apply_envelope_is_larger_than_the_snapshot_alone() {
    let snapshot = json!({"format": 3, "weeks": []});
    let wrapped = serde_json::to_string(&transfer_apply_envelope(&snapshot)).unwrap();
    let bare = serde_json::to_string(&snapshot).unwrap();
    assert_eq!(transfer_apply_bytes(&snapshot), wrapped.len());
    assert!(wrapped.len() > bare.len());
    assert!(transfer_fits(&snapshot));
}

#[test]
fn test_a_snapshot_past_the_write_cap_does_not_fit() {
    let snapshot = json!({"blob": "x".repeat(MAX_BODY)});
    assert!(transfer_apply_bytes(&snapshot) > MAX_BODY);
    assert!(!transfer_fits(&snapshot));
}
