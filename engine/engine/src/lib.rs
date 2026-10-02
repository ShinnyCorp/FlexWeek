//! Pure FlexWeek core. No file, network, clock or randomness.
//! Wide Python signatures stay wide so the port matches the call.

#![allow(clippy::too_many_arguments, clippy::type_complexity)]

pub mod casefold;
pub mod desk;
pub mod error;
pub mod model;
pub mod plan;
pub mod pyprint;
pub mod snapshot;
pub mod solver;
pub mod stored;
pub mod time;
pub mod wide_snap;

pub use error::{EngineError, EngineResult, ErrorKind};
