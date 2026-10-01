//! Errors the Python module turns back into ValueError or LookupError.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorKind {
    Value,
    Lookup,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EngineError {
    pub kind: ErrorKind,
    pub message: String,
}

impl EngineError {
    pub fn value(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::Value,
            message: message.into(),
        }
    }

    pub fn lookup(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::Lookup,
            message: message.into(),
        }
    }
}

pub type EngineResult<T> = Result<T, EngineError>;
