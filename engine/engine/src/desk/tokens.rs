//! Colour maths and design tokens from `desktop/native/tokens.py`.

use serde_json::Value;

use super::cmath;
use crate::error::{EngineError, EngineResult};

pub const SPACING: [i64; 6] = [4, 8, 12, 16, 24, 32];
pub const RADIUS_CONTROL: i64 = 6;
pub const RADIUS_CARD: i64 = 10;
pub const RADIUS_SHEET: i64 = 16;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Shadow {
    pub y: i64,
    pub blur: i64,
    pub opacity: f64,
    pub dark_opacity: f64,
}

pub const SHADOW_SMALL: Shadow = Shadow {
    y: 1,
    blur: 3,
    opacity: 0.08,
    dark_opacity: 0.40,
};
pub const SHADOW_LARGE: Shadow = Shadow {
    y: 12,
    blur: 32,
    opacity: 0.16,
    dark_opacity: 0.50,
};

pub const TYPE_PT: [(&str, f64); 5] = [
    ("caption", 11.0),
    ("body", 13.0),
    ("heading", 15.0),
    ("title", 20.0),
    ("display", 28.0),
];
pub const TEXT_SCALE: [(&str, f64); 3] = [("small", 0.85), ("normal", 1.0), ("large", 1.2)];
pub const WEIGHT_REGULAR: i64 = 400;
pub const WEIGHT_STRONG: i64 = 600;
pub const WEIGHT_NUMBER: i64 = 700;

/// Python 3 `round`: half goes to the even integer.
fn py_round(value: f64) -> f64 {
    value.round_ties_even()
}

fn floating_error() -> EngineError {
    EngineError::overflow("(34, 'Numerical result out of range')")
}

/// `value ** exponent` for floats: a finite number raised to a finite power that overflows raises.
fn power(base: f64, exponent: f64) -> EngineResult<f64> {
    let found = cmath::pow(base, exponent);
    if found.is_infinite() && base.is_finite() && exponent.is_finite() {
        return Err(floating_error());
    }
    Ok(found)
}

/// `round(value)` as an integer.
fn round_int(value: f64) -> EngineResult<i128> {
    if value.is_nan() {
        return Err(EngineError::value("cannot convert float NaN to integer"));
    }
    if value.is_infinite() {
        return Err(EngineError::overflow(
            "cannot convert float infinity to integer",
        ));
    }
    Ok(py_round(value) as i128)
}

/// `format(number, "02x")`.
fn hex2(number: i128) -> String {
    if number < 0 {
        format!("-{:01x}", -number)
    } else {
        format!("{number:02x}")
    }
}

pub fn type_pt(role: &str, scale: &TextScale) -> EngineResult<f64> {
    let factor = match scale {
        TextScale::Named(name) => TEXT_SCALE
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, v)| *v)
            .ok_or_else(|| EngineError::key(name))?,
        TextScale::Factor(f) => *f,
    };
    let base = TYPE_PT
        .iter()
        .find(|(key, _)| *key == role)
        .map(|(_, v)| *v)
        .ok_or_else(|| EngineError::key(role))?;
    Ok(round_int(base * factor * 2.0)? as f64 / 2.0)
}

pub enum TextScale {
    Named(String),
    Factor(f64),
}

pub fn text_knob(body_pt: f64) -> Option<&'static str> {
    TEXT_SCALE.iter().find_map(|(name, _)| {
        (type_pt("body", &TextScale::Named((*name).to_string())).ok() == Some(body_pt))
            .then_some(*name)
    })
}

fn decode(channel: f64) -> EngineResult<f64> {
    if channel <= 0.04045 {
        Ok(channel / 12.92)
    } else {
        power((channel + 0.055) / 1.055, 2.4)
    }
}

fn encode(channel: f64) -> f64 {
    if channel <= 0.0031308 {
        channel * 12.92
    } else {
        1.055 * cmath::pow(channel, 1.0 / 2.4) - 0.055
    }
}

pub fn linear_rgb(colour: &str) -> EngineResult<(f64, f64, f64)> {
    let raw = colour.trim_start_matches('#');
    let pair = |at: usize| -> EngineResult<f64> {
        let part: String = raw.chars().skip(at).take(2).collect();
        Ok(hex_part(&part)? as f64 / 255.0)
    };
    let (red, green, blue) = (pair(0)?, pair(2)?, pair(4)?);
    Ok((decode(red)?, decode(green)?, decode(blue)?))
}

/// `min(max(value, 0.0), 1.0)`, which keeps a NaN as it is.
fn clipped(value: f64) -> f64 {
    let low = if 0.0 > value { 0.0 } else { value };
    if 1.0 < low { 1.0 } else { low }
}

pub fn hex_from_linear(red: f64, green: f64, blue: f64) -> EngineResult<String> {
    let channel = |value: f64| -> EngineResult<i128> { round_int(encode(clipped(value)) * 255.0) };
    Ok(format!(
        "#{}{}{}",
        hex2(channel(red)?),
        hex2(channel(green)?),
        hex2(channel(blue)?)
    ))
}

pub fn oklab_from_linear(red: f64, green: f64, blue: f64) -> (f64, f64, f64) {
    let long = cmath::cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue);
    let medium = cmath::cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue);
    let short = cmath::cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue);
    (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )
}

pub fn linear_from_oklab(light: f64, a: f64, b: f64) -> EngineResult<(f64, f64, f64)> {
    let long = power(light + 0.3963377774 * a + 0.2158037573 * b, 3.0)?;
    let medium = power(light - 0.1055613458 * a - 0.0638541728 * b, 3.0)?;
    let short = power(light - 0.0894841775 * a - 1.2914855480 * b, 3.0)?;
    Ok((
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    ))
}

pub fn oklab(colour: &str) -> EngineResult<(f64, f64, f64)> {
    let (r, g, b) = linear_rgb(colour)?;
    Ok(oklab_from_linear(r, g, b))
}

pub fn oklch(light: f64, chroma: f64, hue: f64) -> EngineResult<String> {
    let angle = hue.to_radians();
    if angle.is_infinite() {
        return Err(EngineError::value("math domain error"));
    }
    let (r, g, b) = linear_from_oklab(
        light,
        chroma * cmath::cos(angle),
        chroma * cmath::sin(angle),
    )?;
    hex_from_linear(r, g, b)
}

/// `_channels` of both colours, which `zip(..., strict=True)` reads before it blends.
pub fn mix(top: &str, bottom: &str, alpha: f64) -> EngineResult<String> {
    let (over, under) = (channels(top)?, channels(bottom)?);
    let blend = |over: i64, under: i64| -> EngineResult<String> {
        Ok(hex2(round_int(
            over as f64 * alpha + under as f64 * (1.0 - alpha),
        )?))
    };
    Ok(format!(
        "#{}{}{}",
        blend(over.0, under.0)?,
        blend(over.1, under.1)?,
        blend(over.2, under.2)?
    ))
}

pub fn luminance(colour: &str) -> EngineResult<f64> {
    let (red, green, blue) = linear_rgb(colour)?;
    Ok(0.2126 * red + 0.7152 * green + 0.0722 * blue)
}

pub fn contrast(first: &str, second: &str) -> EngineResult<f64> {
    contrast_on(first, &Value::String(second.to_string()))
}

/// `contrast` with the second colour as the caller held it: the first is read before a non-string
/// second is refused.
fn contrast_on(first: &str, second: &Value) -> EngineResult<f64> {
    let mut high = luminance(first)?;
    let mut low = luminance(ground_text(second)?)?;
    if high < low {
        std::mem::swap(&mut high, &mut low);
    }
    let divisor = low + 0.05;
    if divisor == 0.0 {
        return Err(EngineError::zero_division("float division by zero"));
    }
    Ok((high + 0.05) / divisor)
}

pub fn oklch_of(colour: &str) -> EngineResult<(f64, f64, f64)> {
    let (light, a, b) = oklab(colour)?;
    let hue = cmath::atan2(b, a).to_degrees().rem_euclid(360.0);
    Ok((
        light,
        cmath::hypot(a, b),
        if hue == 0.0 { 0.0 } else { hue },
    ))
}

/// A ground as text: the `lstrip` of `linear_rgb` needs a string.
fn ground_text(ground: &Value) -> EngineResult<&str> {
    ground
        .as_str()
        .ok_or_else(|| crate::stored::attribute_error(ground, "lstrip"))
}

pub fn fit_lightness(colour: &str, grounds: &[Value], floor: f64) -> EngineResult<String> {
    fn reads(candidate: &str, grounds: &[Value], floor: f64) -> EngineResult<bool> {
        for ground in grounds {
            let ratio = contrast_on(candidate, ground)?;
            if ratio >= floor {
                continue;
            }
            return Ok(false);
        }
        Ok(true)
    }

    if reads(colour, grounds, floor)? {
        return Ok(colour.to_string());
    }
    let (light, chroma, hue) = oklch_of(colour)?;
    let mut found: Vec<(f64, String)> = Vec::new();
    for (end, extreme) in [(0.0, "#000000"), (1.0, "#ffffff")] {
        if !reads(&oklch(end, chroma, hue)?, grounds, floor)? {
            if reads(extreme, grounds, floor)? {
                found.push(((end - light).abs() + 1.0, extreme.to_string()));
            }
            continue;
        }
        let mut fails = light;
        let mut passes = end;
        for _ in 0..40 {
            let middle = (fails + passes) / 2.0;
            if reads(&oklch(middle, chroma, hue)?, grounds, floor)? {
                passes = middle;
            } else {
                fails = middle;
            }
        }
        found.push(((passes - light).abs(), oklch(passes, chroma, hue)?));
    }
    if found.is_empty() {
        // Python's `max` keeps the first of equals, so black wins a tie.
        let worst = |ink: &str| -> EngineResult<f64> {
            let mut least = f64::INFINITY;
            for ground in grounds {
                least = least.min(contrast_on(ink, ground)?);
            }
            Ok(least)
        };
        let ink = if worst("#000000")? >= worst("#ffffff")? {
            "#000000"
        } else {
            "#ffffff"
        };
        return Ok(ink.to_string());
    }
    // Python's `min` over (distance, colour) tuples: equal distances go to the smaller colour text.
    Ok(found
        .into_iter()
        .min_by(|a, b| {
            a.0.partial_cmp(&b.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.1.cmp(&b.1))
        })
        .map(|(_, c)| c)
        .unwrap_or_else(|| colour.to_string()))
}

pub fn mix_oklab(top: &str, bottom: &str, amount: f64) -> EngineResult<String> {
    let over = oklab(top)?;
    let under = oklab(bottom)?;
    let (r, g, b) = linear_from_oklab(
        over.0 * amount + under.0 * (1.0 - amount),
        over.1 * amount + under.1 * (1.0 - amount),
        over.2 * amount + under.2 * (1.0 - amount),
    )?;
    hex_from_linear(r, g, b)
}

const FILL: (f64, f64) = (0.92, 0.045);
const MARK: [(&str, (f64, f64)); 3] = [
    ("light", (0.62, 0.14)),
    ("dark", (0.72, 0.14)),
    ("contrast", (0.78, 0.16)),
];
const GREY_CHROMA: f64 = 0.01;
#[allow(dead_code)]
const SINK: f64 = 0.34;
const HOMEWORK_DARKER: f64 = 0.22;
const SLEEP_FILL_DARKER: f64 = 0.08;
const SLEEP_MARK_DARKER: f64 = 0.12;

pub fn family_colours(
    hue: f64,
    grey: bool,
    homework: bool,
    sleep: bool,
) -> EngineResult<Vec<(String, (String, String))>> {
    let fill = oklch(
        FILL.0 - if sleep { SLEEP_FILL_DARKER } else { 0.0 },
        if grey { GREY_CHROMA } else { FILL.1 },
        hue,
    )?;
    let mut colours = Vec::new();
    for (family, (light, chroma)) in MARK {
        let chroma = if grey { GREY_CHROMA } else { chroma };
        let tone = light - if sleep { SLEEP_MARK_DARKER } else { 0.0 };
        let mark = oklch(
            tone - if homework { HOMEWORK_DARKER } else { 0.0 },
            chroma,
            hue,
        )?;
        let pair = if family == "light" {
            (fill.clone(), mark)
        } else {
            (oklch(tone, chroma, hue)?, mark)
        };
        colours.push((family.to_string(), pair));
    }
    Ok(colours)
}

/// `int(text, 16)` as Python reads it: white space around, a sign, a `0x` prefix, single underscores
/// between digits, and any script's decimal digits.
fn hex_part(raw: &str) -> crate::error::EngineResult<i64> {
    let fail = || {
        crate::error::EngineError::value(format!(
            "invalid literal for int() with base 16: {}",
            crate::time::py_repr(raw)
        ))
    };
    let trimmed = crate::time::py_strip(raw);
    let (negative, unsigned) = match trimmed.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, trimmed.strip_prefix('+').unwrap_or(trimmed)),
    };
    let (prefixed, digits) = match unsigned
        .strip_prefix("0x")
        .or_else(|| unsigned.strip_prefix("0X"))
    {
        Some(rest) => (true, rest),
        None => (false, unsigned),
    };
    let digits = if prefixed {
        digits.strip_prefix('_').unwrap_or(digits)
    } else {
        digits
    };
    let mut value: i64 = 0;
    let mut seen = false;
    let mut after_underscore = false;
    for ch in digits.chars() {
        if ch == '_' {
            if !seen || after_underscore {
                return Err(fail());
            }
            after_underscore = true;
            continue;
        }
        let digit = ch
            .to_digit(16)
            .map(|found| found as i64)
            .or_else(|| crate::time::decimal_digit(ch).map(i64::from))
            .ok_or_else(fail)?;
        value = value
            .checked_mul(16)
            .and_then(|v| v.checked_add(digit))
            .ok_or_else(fail)?;
        seen = true;
        after_underscore = false;
    }
    if !seen || after_underscore {
        return Err(fail());
    }
    Ok(if negative { -value } else { value })
}

/// `_channels(colour)`: the red, green and blue pairs of `#rrggbb`, each read as base-16 text.
pub fn channels(colour: &str) -> crate::error::EngineResult<(i64, i64, i64)> {
    let part = |from: usize| -> String { colour.chars().skip(from).take(2).collect() };
    Ok((
        hex_part(&part(1))?,
        hex_part(&part(3))?,
        hex_part(&part(5))?,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_nan_floor_searches_instead_of_accepting_the_original_colour() {
        assert_eq!(
            fit_lightness("#777777", &[json!("#ffffff")], f64::NAN).unwrap(),
            "#000000"
        );
        assert_eq!(fit_lightness("#777777", &[], f64::NAN).unwrap(), "#777777");
    }

    #[test]
    fn hex_round_trip_matches_python_encode() {
        assert_eq!(hex_from_linear(0.5, 0.5, 0.5).unwrap(), "#bcbcbc");
    }
}
