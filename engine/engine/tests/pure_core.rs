//! Guarantee 4: the core does not touch files, the network, the clock, the
//! environment, or randomness. A `#[cfg(test)]` module is not the core.

use std::path::Path;

const FORBIDDEN: &[&str] = &[
    "std::fs",
    "std::env",
    "std::net",
    "std::process",
    "SystemTime",
    "File::",
];

/// Words, not pieces of a longer name. `randomness` is not `rand`.
const FORBIDDEN_WORDS: &[&str] = &["Instant", "canonicalize", "rand"];

/// `desk/cmath.rs` loads the platform C maths library because CPython's colour
/// code calls those same functions. These are the only symbols that file may use
/// to do it.
const CMATH_SYMBOLS: &[&str] = &["dlopen", "dlsym", "LoadLibraryA", "GetProcAddress"];

fn ident_at(text: &str, index: usize) -> bool {
    text[..index]
        .chars()
        .next_back()
        .is_some_and(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

fn word_at(line: &str, word: &str) -> bool {
    let mut rest = line;
    let mut offset = 0usize;
    while let Some(found) = rest.find(word) {
        let start = offset + found;
        let end = start + word.len();
        let before_ok = !ident_at(line, start);
        let after_ok = !line[end..]
            .chars()
            .next()
            .is_some_and(|ch| ch.is_ascii_alphanumeric() || ch == '_');
        if before_ok && after_ok {
            return true;
        }
        let next = found + word.len();
        offset += next;
        rest = &rest[next..];
    }
    false
}

fn without_cfg_test(source: &str) -> String {
    let lines: Vec<&str> = source.lines().collect();
    let mut out = String::new();
    let mut index = 0;
    let mut depth = 0i32;
    while index < lines.len() {
        let trimmed = lines[index].trim();
        if trimmed.starts_with("#[cfg(test)]") || trimmed.starts_with("#[cfg(test,") {
            index += 1;
            while index < lines.len() && lines[index].trim().starts_with('#') {
                index += 1;
            }
            if index >= lines.len() {
                break;
            }
            let start_depth = depth;
            let mut started = false;
            loop {
                for ch in lines[index].chars() {
                    if ch == '{' {
                        depth += 1;
                        started = true;
                    }
                    if ch == '}' {
                        depth -= 1;
                    }
                }
                index += 1;
                if started && depth == start_depth || index >= lines.len() {
                    break;
                }
            }
            continue;
        }
        for ch in lines[index].chars() {
            if ch == '{' {
                depth += 1;
            }
            if ch == '}' {
                depth -= 1;
            }
        }
        out.push_str(lines[index]);
        out.push('\n');
        index += 1;
    }
    out
}

fn hits(relative: &str, source: &str) -> Vec<String> {
    let mut found = Vec::new();
    for (number, line) in without_cfg_test(source).lines().enumerate() {
        let code = line.split("//").next().unwrap_or(line);
        if relative == "desk/cmath.rs" && CMATH_SYMBOLS.iter().any(|symbol| code.contains(symbol)) {
            continue;
        }
        for needle in FORBIDDEN {
            if code.contains(needle) {
                found.push(format!("{relative}:{}: {needle}", number + 1));
            }
        }
        for word in FORBIDDEN_WORDS {
            if word_at(code, word) {
                found.push(format!("{relative}:{}: {word}", number + 1));
            }
        }
    }
    found
}

#[test]
fn the_core_does_not_touch_files_the_clock_or_randomness() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut found = Vec::new();
    for entry in walk(&root) {
        let relative = entry
            .strip_prefix(&root)
            .unwrap()
            .to_string_lossy()
            .replace('\\', "/");
        let source = std::fs::read_to_string(&entry).unwrap();
        found.extend(hits(&relative, &source));
    }
    let cmath = std::fs::read_to_string(root.join("desk/cmath.rs")).unwrap();
    for symbol in CMATH_SYMBOLS {
        assert!(
            cmath.contains(symbol),
            "desk/cmath.rs no longer uses {symbol}; drop it from the allow list"
        );
    }
    assert!(
        found.is_empty(),
        "the core reached outside itself:\n{}",
        found.join("\n")
    );
}

fn walk(dir: &Path) -> Vec<std::path::PathBuf> {
    let mut files = Vec::new();
    for entry in std::fs::read_dir(dir).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if path.is_dir() {
            files.extend(walk(&path));
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            files.push(path);
        }
    }
    files.sort();
    files
}
