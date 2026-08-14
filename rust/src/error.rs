//! The error vocabulary, and the exit codes it maps to.
//!
//! The same table the Python side uses, from the whitepaper's chapter 38. Two
//! implementations that agreed about *whether* an archive is valid but not about
//! *why* would give the differential fuzzer nothing to compare beyond a boolean —
//! and "both refused" is a much weaker signal than "both refused for the same
//! reason".

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    InvalidInput,
    UnsupportedCapability,
    ManifestInvalid,
    IntegrityFailure,
    ResourceLimitExceeded,
    UnsafeObject,
    FidelityDegraded,
}

impl Kind {
    pub fn exit_code(self) -> i32 {
        match self {
            Kind::InvalidInput => 2,
            Kind::UnsupportedCapability => 3,
            Kind::ManifestInvalid => 4,
            Kind::IntegrityFailure => 5,
            Kind::ResourceLimitExceeded => 8,
            Kind::UnsafeObject => 9,
            Kind::FidelityDegraded => 11,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Kind::InvalidInput => "invalid-input",
            Kind::UnsupportedCapability => "unsupported-capability",
            Kind::ManifestInvalid => "manifest-invalid",
            Kind::IntegrityFailure => "integrity-failure",
            Kind::ResourceLimitExceeded => "resource-limit-exceeded",
            Kind::UnsafeObject => "unsafe-object",
            Kind::FidelityDegraded => "fidelity-degraded",
        }
    }
}

#[derive(Debug)]
pub struct Error {
    pub kind: Kind,
    pub message: String,
}

impl Error {
    pub fn new(kind: Kind, message: impl Into<String>) -> Self {
        Error {
            kind,
            message: message.into(),
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.kind.name(), self.message)
    }
}

pub type Result<T> = std::result::Result<T, Error>;
