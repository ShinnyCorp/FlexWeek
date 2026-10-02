//! Errors the Python module turns back into ValueError or LookupError.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorKind {
    Value,
    Lookup,
    /// `KeyError`. The message is the missing key; Python's `str` adds the quotes.
    Key,
    Index,
    Overflow,
    ZeroDivision,
    /// `TypeError` and `AttributeError`: what Python raised on a stored value of the wrong type.
    Type,
    Attribute,
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

    pub fn key(name: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::Key,
            message: name.into(),
        }
    }

    pub fn index(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::Index,
            message: message.into(),
        }
    }

    pub fn overflow(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::Overflow,
            message: message.into(),
        }
    }

    pub fn zero_division(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::ZeroDivision,
            message: message.into(),
        }
    }
}

pub type EngineResult<T> = Result<T, EngineError>;
