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
    /// `KeyError` of a key that is not text; the message is its Python repr.
    KeyRepr,
    /// A name a saved look cannot have, or one no saved look has.
    LookName,
    /// `StopIteration`, from `next(...)` on nothing.
    Stop,
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

    /// A `KeyError` for any key, given as Python prints it (`7`, `None`, `1.5`).
    pub fn key_repr(repr: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::KeyRepr,
            message: repr.into(),
        }
    }

    pub fn look_name(message: impl Into<String>) -> Self {
        Self {
            kind: ErrorKind::LookName,
            message: message.into(),
        }
    }

    pub fn stop() -> Self {
        Self {
            kind: ErrorKind::Stop,
            message: String::new(),
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
