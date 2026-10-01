//! Colour maths and design tokens from `desktop/native/tokens.py`.

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

pub fn type_pt(role: &str, scale: TextScale) -> f64 {
    let factor = match scale {
        TextScale::Named(name) => TEXT_SCALE
            .iter()
            .find(|(key, _)| *key == name)
            .map(|(_, v)| *v)
            .unwrap_or(1.0),
        TextScale::Factor(f) => f,
    };
    let base = TYPE_PT
        .iter()
        .find(|(key, _)| *key == role)
        .map(|(_, v)| *v)
        .unwrap_or(13.0);
    (base * factor * 2.0).round() / 2.0
}

pub enum TextScale<'a> {
    Named(&'a str),
    Factor(f64),
}

impl<'a> From<&'a str> for TextScale<'a> {
    fn from(s: &'a str) -> Self {
        TextScale::Named(s)
    }
}

impl From<f64> for TextScale<'static> {
    fn from(f: f64) -> Self {
        TextScale::Factor(f)
    }
}

pub fn text_knob(body_pt: f64) -> Option<&'static str> {
    TEXT_SCALE.iter().find_map(|(name, _)| {
        if type_pt("body", TextScale::Named(name)) == body_pt {
            Some(*name)
        } else {
            None
        }
    })
}

fn decode(channel: f64) -> f64 {
    if channel <= 0.04045 {
        channel / 12.92
    } else {
        ((channel + 0.055) / 1.055).powf(2.4)
    }
}

fn encode(channel: f64) -> f64 {
    if channel <= 0.0031308 {
        channel * 12.92
    } else {
        1.055 * channel.powf(1.0 / 2.4) - 0.055
    }
}

pub fn linear_rgb(colour: &str) -> (f64, f64, f64) {
    let raw = colour.trim_start_matches('#');
    let parse = |at: usize| i64::from_str_radix(&raw[at..at + 2], 16).unwrap_or(0) as f64 / 255.0;
    (decode(parse(0)), decode(parse(2)), decode(parse(4)))
}

pub fn hex_from_linear(red: f64, green: f64, blue: f64) -> String {
    let channel = |value: f64| -> i64 { (encode(value.clamp(0.0, 1.0)) * 255.0).round() as i64 };
    format!(
        "#{:02x}{:02x}{:02x}",
        channel(red),
        channel(green),
        channel(blue)
    )
}

pub fn oklab_from_linear(red: f64, green: f64, blue: f64) -> (f64, f64, f64) {
    let long = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue).cbrt();
    let medium = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue).cbrt();
    let short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue).cbrt();
    (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )
}

pub fn linear_from_oklab(light: f64, a: f64, b: f64) -> (f64, f64, f64) {
    let long = (light + 0.3963377774 * a + 0.2158037573 * b).powi(3);
    let medium = (light - 0.1055613458 * a - 0.0638541728 * b).powi(3);
    let short = (light - 0.0894841775 * a - 1.2914855480 * b).powi(3);
    (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )
}

pub fn oklab(colour: &str) -> (f64, f64, f64) {
    let (r, g, b) = linear_rgb(colour);
    oklab_from_linear(r, g, b)
}

pub fn oklch(light: f64, chroma: f64, hue: f64) -> String {
    let angle = hue.to_radians();
    let (r, g, b) = linear_from_oklab(light, chroma * angle.cos(), chroma * angle.sin());
    hex_from_linear(r, g, b)
}

fn channels(colour: &str) -> (i64, i64, i64) {
    (
        i64::from_str_radix(&colour[1..3], 16).unwrap_or(0),
        i64::from_str_radix(&colour[3..5], 16).unwrap_or(0),
        i64::from_str_radix(&colour[5..7], 16).unwrap_or(0),
    )
}

pub fn mix(top: &str, bottom: &str, alpha: f64) -> String {
    let (tr, tg, tb) = channels(top);
    let (br, bg, bb) = channels(bottom);
    let blend = |over: i64, under: i64| -> i64 {
        (over as f64 * alpha + under as f64 * (1.0 - alpha)).round() as i64
    };
    format!(
        "#{:02x}{:02x}{:02x}",
        blend(tr, br),
        blend(tg, bg),
        blend(tb, bb)
    )
}

pub fn luminance(colour: &str) -> f64 {
    let (red, green, blue) = linear_rgb(colour);
    0.2126 * red + 0.7152 * green + 0.0722 * blue
}

pub fn contrast(first: &str, second: &str) -> f64 {
    let mut high = luminance(first);
    let mut low = luminance(second);
    if high < low {
        std::mem::swap(&mut high, &mut low);
    }
    (high + 0.05) / (low + 0.05)
}

pub fn oklch_of(colour: &str) -> (f64, f64, f64) {
    let (light, a, b) = oklab(colour);
    (
        light,
        (a * a + b * b).sqrt(),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    )
}

pub fn fit_lightness(colour: &str, grounds: &[&str], floor: f64) -> String {
    fn reads(candidate: &str, grounds: &[&str], floor: f64) -> bool {
        grounds
            .iter()
            .all(|ground| contrast(candidate, ground) >= floor)
    }

    if reads(colour, grounds, floor) {
        return colour.to_string();
    }
    let (light, chroma, hue) = oklch_of(colour);
    let mut found: Vec<(f64, String)> = Vec::new();
    for (end, extreme) in [(0.0, "#000000"), (1.0, "#ffffff")] {
        if !reads(&oklch(end, chroma, hue), grounds, floor) {
            if reads(extreme, grounds, floor) {
                found.push(((end - light).abs() + 1.0, extreme.to_string()));
            }
            continue;
        }
        let mut fails = light;
        let mut passes = end;
        for _ in 0..40 {
            let middle = (fails + passes) / 2.0;
            if reads(&oklch(middle, chroma, hue), grounds, floor) {
                passes = middle;
            } else {
                fails = middle;
            }
        }
        found.push(((passes - light).abs(), oklch(passes, chroma, hue)));
    }
    if found.is_empty() {
        let black = "#000000";
        let white = "#ffffff";
        if contrast(black, grounds[0]) >= contrast(white, grounds[0]) {
            return black.to_string();
        }
        return white.to_string();
    }
    found
        .into_iter()
        .min_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(_, c)| c)
        .unwrap_or_else(|| colour.to_string())
}

pub fn mix_oklab(top: &str, bottom: &str, amount: f64) -> String {
    let over = oklab(top);
    let under = oklab(bottom);
    let (r, g, b) = linear_from_oklab(
        over.0 * amount + under.0 * (1.0 - amount),
        over.1 * amount + under.1 * (1.0 - amount),
        over.2 * amount + under.2 * (1.0 - amount),
    );
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
) -> Vec<(String, (String, String))> {
    let fill = oklch(
        FILL.0 - if sleep { SLEEP_FILL_DARKER } else { 0.0 },
        if grey { GREY_CHROMA } else { FILL.1 },
        hue,
    );
    let mut colours = Vec::new();
    for (family, (light, chroma)) in MARK {
        let chroma = if grey { GREY_CHROMA } else { chroma };
        let tone = light - if sleep { SLEEP_MARK_DARKER } else { 0.0 };
        let mark = oklch(
            tone - if homework { HOMEWORK_DARKER } else { 0.0 },
            chroma,
            hue,
        );
        let pair = if family == "light" {
            (fill.clone(), mark)
        } else {
            (oklch(tone, chroma, hue), mark)
        };
        colours.push((family.to_string(), pair));
    }
    colours
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_round_trip_matches_python_encode() {
        assert_eq!(hex_from_linear(0.5, 0.5, 0.5), "#bcbcbc");
    }
}
