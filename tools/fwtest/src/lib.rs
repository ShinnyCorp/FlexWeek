//! fwtest library. The contract is `docs/tooling/fwtest.md`.

pub mod clean;
pub mod contain;
pub mod edits;
pub mod gate;
pub mod hidden;
pub mod identity;
pub mod job;
pub mod mutate;
pub mod queue;
pub mod rebuild;
pub mod rig;
pub mod state;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExitCode(pub u8);

impl ExitCode {
    pub const OK: Self = Self(0);
    pub const CHECK_FAILED: Self = Self(1);
    pub const USAGE: Self = Self(2);
}
