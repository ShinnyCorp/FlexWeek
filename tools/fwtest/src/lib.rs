//! fwtest library. The contract is `docs/tooling/fwtest.md`.

pub mod clean;
pub mod contain;
pub mod identity;
pub mod job;
pub mod queue;
pub mod state;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExitCode(pub u8);

impl ExitCode {
    pub const OK: Self = Self(0);
    pub const CHECK_FAILED: Self = Self(1);
    pub const USAGE: Self = Self(2);
}
