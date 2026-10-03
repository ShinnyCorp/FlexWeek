//! Python's `snap_minutes` for integers that do not fit in `i64`.
//!
//! `int(round(value / 15) * 15)` rounds the IEEE-754 quotient (half to even),
//! then the three grid clamps. Values that fit in `i64` stay on `plan::snap_minutes`.

use std::cmp::Ordering;

use crate::{EngineError, EngineResult, ErrorKind};

const SLOT: u32 = 15;
const FLOAT_OVERFLOW: &str = "integer division result too large for a float";

pub fn snap_minutes_wide(value: &str, minimum: &str, maximum: &str) -> EngineResult<String> {
    let value = Digits::parse(value)?;
    let minimum = Digits::parse(minimum)?;
    let maximum = Digits::parse(maximum)?;
    let mut snapped = round_div_slot(&value)?.mul_u32(SLOT);
    if snapped.cmp(&minimum) == Ordering::Less {
        snapped = ceil_slot(&minimum);
    }
    if snapped.cmp(&maximum) == Ordering::Greater {
        snapped = floor_slot(&maximum);
    }
    let slot = Digits::from_u8(SLOT as u8);
    if snapped.cmp(&slot) == Ordering::Less {
        snapped = slot;
    }
    Ok(snapped.to_string())
}

fn round_div_slot(value: &Digits) -> EngineResult<Digits> {
    if value.is_zero() {
        return Ok(Digits::zero());
    }
    let rounded = match value.abs().to_u64() {
        Some(small) => round_div_slot_u64(small)?,
        None => round_div_slot_big(&value.abs())?,
    };
    Ok(if value.neg {
        rounded.negated()
    } else {
        rounded
    })
}

fn round_div_slot_u64(n: u64) -> EngineResult<Digits> {
    if n < SLOT as u64 {
        return Ok(Digits::from_i64(py_round(n as f64 / SLOT as f64)));
    }
    let mut exp = floor_log2_div_slot_u64(n);
    if exp >= 1024 {
        return Err(float_overflow());
    }
    let mut mant = if exp >= 52 {
        let shift = (exp - 52) as u32;
        let q = n / SLOT as u64;
        let r = n % SLOT as u64;
        let split = if shift == 0 {
            (q, 0u64)
        } else {
            (q >> shift, q & ((1u64 << shift) - 1))
        };
        let rem = (split.1 as u128) * SLOT as u128 + r as u128;
        let mut mant = split.0 as u128;
        let denom = (SLOT as u128) << shift;
        if rem * 2 > denom || (rem * 2 == denom && mant % 2 == 1) {
            mant += 1;
        }
        mant
    } else {
        let scaled = (n as u128) << ((52 - exp) as u32);
        let mut mant = scaled / SLOT as u128;
        let rem = scaled % SLOT as u128;
        if rem * 2 > SLOT as u128 {
            mant += 1;
        }
        mant
    };
    if mant == 1 << 53 {
        mant = 1 << 52;
        exp += 1;
    }
    if exp >= 1024 {
        return Err(float_overflow());
    }
    if !(1 << 52..1 << 53).contains(&mant) {
        return Err(EngineError::value(format!("mantissa {mant} at exp {exp}")));
    }
    if exp >= 53 {
        return Ok(Digits::from_u128(mant << (exp - 52) as u32));
    }
    Ok(Digits::from_i64(py_round(f64_from_mant_exp(
        mant as u64,
        exp,
    ))))
}

fn round_div_slot_big(n: &Digits) -> EngineResult<Digits> {
    let mut exp = floor_log2_div_slot(n);
    if exp >= 1024 {
        return Err(float_overflow());
    }
    let shift = (exp - 52) as u32;
    let (q, r) = n.divmod_u32(SLOT);
    let (mut mant, r2) = q.divmod_pow2(shift);
    let rem = r2.mul_u32(SLOT).add(&Digits::from_u32(r));
    let twice = rem.mul_u32(2);
    let denom = Digits::from_u32(SLOT).shl_pow2(shift);
    if twice.cmp(&denom) == Ordering::Greater || (twice == denom && mant.is_odd()) {
        mant = mant.add(&Digits::from_u8(1));
    }
    let Some(mut mant_u) = mant.to_u64() else {
        return Err(EngineError::value(format!("mantissa {mant} at exp {exp}")));
    };
    if mant_u == 1 << 53 {
        mant_u = 1 << 52;
        exp += 1;
    }
    if exp >= 1024 {
        return Err(float_overflow());
    }
    if !(1 << 52..1 << 53).contains(&mant_u) {
        return Err(EngineError::value(format!(
            "mantissa {mant_u} at exp {exp}"
        )));
    }
    Ok(Digits::from_u64(mant_u).shl_pow2((exp - 52) as u32))
}

fn floor_log2_div_slot_u64(n: u64) -> i32 {
    let bits = 63 - n.leading_zeros() as i32;
    let thresh = (SLOT as u128) << (bits - 3);
    if n as u128 >= thresh {
        bits - 3
    } else {
        bits - 4
    }
}

fn floor_log2_div_slot(n: &Digits) -> i32 {
    let bits = n.floor_log2() as i32;
    let thresh = Digits::from_u32(SLOT).shl_pow2((bits - 3) as u32);
    if n.cmp_abs(&thresh) != Ordering::Less {
        bits - 3
    } else {
        bits - 4
    }
}

fn py_round(value: f64) -> i64 {
    let floor = value.floor();
    let diff = value - floor;
    let base = floor as i64;
    if diff < 0.5 {
        base
    } else if diff > 0.5 || base.rem_euclid(2) != 0 {
        base + 1
    } else {
        base
    }
}

fn f64_from_mant_exp(mant: u64, exp: i32) -> f64 {
    let frac = mant - (1u64 << 52);
    let bits = ((exp as u64 + 1023) << 52) | frac;
    f64::from_bits(bits)
}

fn ceil_slot(n: &Digits) -> Digits {
    let rem = n.rem_euclid(SLOT);
    let add = (SLOT - rem) % SLOT;
    n.add(&Digits::from_u32(add))
}

fn floor_slot(n: &Digits) -> Digits {
    n.sub(&Digits::from_u32(n.rem_euclid(SLOT)))
}

fn float_overflow() -> EngineError {
    EngineError {
        kind: ErrorKind::Overflow,
        message: FLOAT_OVERFLOW.to_string(),
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Digits {
    digs: Vec<u8>,
    neg: bool,
}

impl Digits {
    fn zero() -> Self {
        Self {
            digs: Vec::new(),
            neg: false,
        }
    }

    fn parse(text: &str) -> EngineResult<Self> {
        let (neg, digits) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text),
        };
        if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
            return Err(EngineError::value(format!(
                "invalid literal for int() with base 10: {text}"
            )));
        }
        let digits = digits.trim_start_matches('0');
        if digits.is_empty() {
            return Ok(Self::zero());
        }
        Ok(Self {
            digs: digits.bytes().rev().map(|byte| byte - b'0').collect(),
            neg,
        })
    }

    fn from_u8(n: u8) -> Self {
        Self::from_u64(u64::from(n))
    }

    fn from_u32(n: u32) -> Self {
        Self::from_u64(u64::from(n))
    }

    fn from_u64(mut n: u64) -> Self {
        if n == 0 {
            return Self::zero();
        }
        let mut digs = Vec::new();
        while n > 0 {
            digs.push((n % 10) as u8);
            n /= 10;
        }
        Self { digs, neg: false }
    }

    fn from_u128(mut n: u128) -> Self {
        if n == 0 {
            return Self::zero();
        }
        let mut digs = Vec::new();
        while n > 0 {
            digs.push((n % 10) as u8);
            n /= 10;
        }
        Self { digs, neg: false }
    }

    fn from_i64(n: i64) -> Self {
        let mut out = Self::from_u64(n.unsigned_abs());
        out.neg = n < 0;
        out
    }

    fn is_zero(&self) -> bool {
        self.digs.is_empty()
    }

    fn is_odd(&self) -> bool {
        self.digs.first().copied().unwrap_or(0) % 2 == 1
    }

    fn abs(&self) -> Self {
        let mut out = self.clone();
        out.neg = false;
        out
    }

    fn negated(&self) -> Self {
        let mut out = self.clone();
        if !out.is_zero() {
            out.neg = !out.neg;
        }
        out
    }

    fn to_u64(&self) -> Option<u64> {
        if self.neg {
            return None;
        }
        let mut acc = 0u64;
        for digit in self.digs.iter().rev() {
            acc = acc.checked_mul(10)?.checked_add(u64::from(*digit))?;
        }
        Some(acc)
    }

    fn cmp_abs(&self, other: &Self) -> Ordering {
        match self.digs.len().cmp(&other.digs.len()) {
            Ordering::Equal => {}
            order => return order,
        }
        for (left, right) in self.digs.iter().rev().zip(other.digs.iter().rev()) {
            match left.cmp(right) {
                Ordering::Equal => {}
                order => return order,
            }
        }
        Ordering::Equal
    }

    fn add(&self, other: &Self) -> Self {
        if self.neg == other.neg {
            let mut out = self.add_abs(other);
            out.neg = self.neg && !out.is_zero();
            return out;
        }
        if self.cmp_abs(other) != Ordering::Less {
            let mut out = self.sub_abs(other);
            out.neg = self.neg && !out.is_zero();
            out
        } else {
            let mut out = other.sub_abs(self);
            out.neg = other.neg && !out.is_zero();
            out
        }
    }

    fn sub(&self, other: &Self) -> Self {
        self.add(&other.negated())
    }

    fn add_abs(&self, other: &Self) -> Self {
        let mut digs = Vec::with_capacity(self.digs.len().max(other.digs.len()) + 1);
        let mut carry = 0u16;
        for index in 0..self.digs.len().max(other.digs.len()) {
            let left = u16::from(*self.digs.get(index).unwrap_or(&0));
            let right = u16::from(*other.digs.get(index).unwrap_or(&0));
            let sum = left + right + carry;
            digs.push((sum % 10) as u8);
            carry = sum / 10;
        }
        if carry > 0 {
            digs.push(carry as u8);
        }
        let mut out = Self { digs, neg: false };
        out.normalize();
        out
    }

    fn sub_abs(&self, other: &Self) -> Self {
        let mut digs = Vec::with_capacity(self.digs.len());
        let mut borrow = 0i16;
        for index in 0..self.digs.len() {
            let right = i16::from(*other.digs.get(index).unwrap_or(&0));
            let mut diff = i16::from(self.digs[index]) - right - borrow;
            if diff < 0 {
                diff += 10;
                borrow = 1;
            } else {
                borrow = 0;
            }
            digs.push(diff as u8);
        }
        let mut out = Self { digs, neg: false };
        out.normalize();
        out
    }

    fn mul_u32(&self, factor: u32) -> Self {
        if self.is_zero() || factor == 0 {
            return Self::zero();
        }
        let mut digs = Vec::with_capacity(self.digs.len() + 10);
        let mut carry = 0u32;
        for digit in &self.digs {
            let value = u32::from(*digit) * factor + carry;
            digs.push((value % 10) as u8);
            carry = value / 10;
        }
        while carry > 0 {
            digs.push((carry % 10) as u8);
            carry /= 10;
        }
        Self {
            digs,
            neg: self.neg,
        }
    }

    fn divmod_u32(&self, divisor: u32) -> (Self, u32) {
        let mut rem = 0u32;
        let mut digs = vec![0u8; self.digs.len()];
        for index in (0..self.digs.len()).rev() {
            let cur = rem * 10 + u32::from(self.digs[index]);
            digs[index] = (cur / divisor) as u8;
            rem = cur % divisor;
        }
        let mut quot = Self { digs, neg: false };
        quot.normalize();
        (quot, rem)
    }

    fn divmod_pow2(&self, shift: u32) -> (Self, Self) {
        let mut quot = self.abs();
        let mut bits = Vec::with_capacity(shift as usize);
        for _ in 0..shift {
            let (next, bit) = quot.divmod_u32(2);
            bits.push(bit as u8);
            quot = next;
        }
        (quot, Self::from_le_bits(&bits))
    }

    fn from_le_bits(bits: &[u8]) -> Self {
        let mut out = Self::zero();
        for bit in bits.iter().rev() {
            out = out.mul_u32(2);
            if *bit != 0 {
                out = out.add(&Self::from_u8(1));
            }
        }
        out
    }

    fn shl_pow2(&self, shift: u32) -> Self {
        let mut out = self.abs();
        for _ in 0..shift {
            out = out.mul_u32(2);
        }
        if self.neg && !out.is_zero() {
            out.neg = true;
        }
        out
    }

    fn floor_log2(&self) -> u32 {
        let mut n = self.abs();
        let mut bits = 0u32;
        while !n.is_zero() {
            n = n.divmod_u32(2).0;
            bits += 1;
        }
        bits - 1
    }

    fn rem_euclid(&self, divisor: u32) -> u32 {
        let rem = self.abs().divmod_u32(divisor).1;
        if self.neg && rem != 0 {
            divisor - rem
        } else {
            rem
        }
    }

    fn normalize(&mut self) {
        while self.digs.last() == Some(&0) {
            self.digs.pop();
        }
        if self.digs.is_empty() {
            self.neg = false;
        }
    }
}

impl Ord for Digits {
    fn cmp(&self, other: &Self) -> Ordering {
        match (self.neg, other.neg) {
            (false, true) => Ordering::Greater,
            (true, false) => Ordering::Less,
            (false, false) => self.cmp_abs(other),
            (true, true) => other.cmp_abs(self),
        }
    }
}

impl PartialOrd for Digits {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl std::fmt::Display for Digits {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.is_zero() {
            return f.write_str("0");
        }
        if self.neg {
            f.write_str("-")?;
        }
        for digit in self.digs.iter().rev() {
            write!(f, "{digit}")?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snap(value: &str, minimum: &str, maximum: &str) -> String {
        snap_minutes_wide(value, minimum, maximum).unwrap_or_else(|err| panic!("{err:?}"))
    }

    fn dec_pow2(exp: u32) -> String {
        let mut digits = vec![1u8];
        for _ in 0..exp {
            let mut carry = 0u16;
            for digit in &mut digits {
                let value = u16::from(*digit) * 2 + carry;
                *digit = (value % 10) as u8;
                carry = value / 10;
            }
            if carry > 0 {
                digits.push(carry as u8);
            }
        }
        digits
            .into_iter()
            .rev()
            .map(|digit| char::from(b'0' + digit))
            .collect()
    }

    #[test]
    fn small_grid_matches_python() {
        let cases = [
            ("17", "1", "180", "15"),
            ("7", "1", "180", "15"),
            ("185", "1", "180", "180"),
            ("25", "1", "180", "30"),
            ("5", "1", "60", "15"),
            ("1", "1", "180", "15"),
            ("30", "1", "180", "30"),
            ("22", "1", "180", "15"),
            ("23", "1", "180", "30"),
            ("0", "1", "180", "15"),
            ("-7", "1", "180", "15"),
            ("40", "16", "40", "30"),
            ("10", "-3", "10", "15"),
            ("100", "-20", "-5", "15"),
            ("3", "1", "10", "15"),
            ("15", "1", "180", "15"),
            ("8", "8", "8", "15"),
            ("1000000", "-40", "50", "45"),
        ];
        for (value, low, high, want) in cases {
            assert_eq!(snap(value, low, high), want, "{value} {low} {high}");
        }
    }

    #[test]
    fn wide_integers_match_python_round_half_even() {
        let two_63 = "9223372036854775808";
        let two_100 = "1267650600228229401496703205376";
        let cases = [
            (
                "10000000000000000000",
                "1",
                "100000000000000000000",
                "9999999999999999360",
            ),
            ("10000000000000000000", "1", "180", "180"),
            ("-10000000000000000000", "1", "180", "15"),
            (
                "100000000000000000000",
                "0",
                "1000000000000000000000",
                "100000000000000005120",
            ),
            (two_63, "1", two_63, "9223372036854775680"),
            (two_63, "1", "180", "180"),
            ("-9223372036854775808", "-100", "180", "15"),
            (
                "1000000000000000000",
                "1000000000000000000",
                "1000000000000000050",
                "1000000000000000005",
            ),
            (two_100, "1", two_100, "1267650600228229383904517160960"),
            (
                "1208925819614629174706183",
                "1",
                two_100,
                "1208925819614629157928960",
            ),
            ("-10000000000000000000", "-10000000000000000000", "-1", "15"),
            (
                "9007199254740995",
                "1",
                "1152921504606846976",
                "9007199254740990",
            ),
            (
                "9007199254740992",
                "1",
                "1000000000000000000000000000000",
                "9007199254740990",
            ),
            (
                "18446744073709551615",
                "1",
                "100000000000000000000",
                "18446744073709551360",
            ),
            (
                "18446744073709551616",
                "1",
                "100000000000000000000",
                "18446744073709551360",
            ),
            (
                "1208925819614629174706176",
                "1",
                "1000000000000000000000000000000",
                "1208925819614629157928960",
            ),
            (
                "-1208925819614629174706176",
                "1",
                "1000000000000000000000000000000",
                "15",
            ),
        ];
        for (value, low, high, want) in cases {
            assert_eq!(snap(value, low, high), want, "{value}");
        }
    }

    #[test]
    fn two_to_the_1027_matches_python_and_the_next_power_overflows() {
        let value = dec_pow2(1027);
        let want = "1438154507889852706225041057284021670330654452785459597512928044907285991418535280689548899889619630319381256112614135967845849708590380540218399561179856387630425164550609679010361027299111987780247449173050174324171638013300463118483200333117914008418251400996248810848368898750277314015097898333553693818880";
        assert_eq!(snap(&value, "1", &value), want);
        let err = snap_minutes_wide(&dec_pow2(1028), "1", "1").unwrap_err();
        assert_eq!(err.kind, ErrorKind::Overflow);
        assert_eq!(err.message, FLOAT_OVERFLOW);
        let huge = format!("1{}", "0".repeat(400));
        let err = snap_minutes_wide(&huge, "1", &huge).unwrap_err();
        assert_eq!(err.kind, ErrorKind::Overflow);
        assert_eq!(err.message, FLOAT_OVERFLOW);
    }
}
