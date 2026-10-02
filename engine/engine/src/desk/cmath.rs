//! The maths functions CPython's colour code calls, computed the way CPython computes them.
//!
//! `math.cbrt`, `math.cos`, `math.sin`, `math.atan2` and float `**` call the platform's C library,
//! so the engine calls that same library to get the same last bit. The functions are looked up at
//! run time: linked by name, `cbrt` binds to the copy Rust's `compiler_builtins` puts inside the
//! module, which is one bit away from glibc's on some inputs. `math.hypot` is CPython's own code,
//! ported below.

use std::ffi::{CStr, c_void};
use std::sync::OnceLock;

struct Functions {
    cbrt: extern "C" fn(f64) -> f64,
    pow: extern "C" fn(f64, f64) -> f64,
    atan2: extern "C" fn(f64, f64) -> f64,
    cos: extern "C" fn(f64) -> f64,
    sin: extern "C" fn(f64) -> f64,
}

#[cfg(target_os = "linux")]
mod platform {
    use std::ffi::{CStr, c_char, c_int, c_void};

    pub const LIBRARY: &CStr = c"libm.so.6";
    const RTLD_NOW: c_int = 2;

    unsafe extern "C" {
        fn dlopen(filename: *const c_char, flags: c_int) -> *mut c_void;
        fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    }

    pub fn open() -> *mut c_void {
        // SAFETY: a NUL-terminated name; loading libm runs no code of ours.
        unsafe { dlopen(LIBRARY.as_ptr(), RTLD_NOW) }
    }

    pub fn symbol(library: *mut c_void, name: &CStr) -> *mut c_void {
        // SAFETY: `library` came from `dlopen` and is never closed.
        unsafe { dlsym(library, name.as_ptr()) }
    }
}

// CPython on Windows links the Universal CRT dynamically, which lives in ucrtbase.dll.
#[cfg(windows)]
mod platform {
    use std::ffi::{CStr, c_char, c_void};

    pub const LIBRARY: &CStr = c"ucrtbase.dll";

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn LoadLibraryA(name: *const c_char) -> *mut c_void;
        fn GetProcAddress(module: *mut c_void, name: *const c_char) -> *mut c_void;
    }

    pub fn open() -> *mut c_void {
        // SAFETY: a NUL-terminated name of a system library.
        unsafe { LoadLibraryA(LIBRARY.as_ptr()) }
    }

    pub fn symbol(library: *mut c_void, name: &CStr) -> *mut c_void {
        // SAFETY: `library` came from `LoadLibraryA` and is never freed.
        unsafe { GetProcAddress(library, name.as_ptr()) }
    }
}

#[cfg(not(any(target_os = "linux", windows)))]
compile_error!("name the C maths library CPython uses on this platform in desk/cmath.rs");

fn functions() -> &'static Functions {
    static FUNCTIONS: OnceLock<Functions> = OnceLock::new();
    FUNCTIONS.get_or_init(|| {
        let library = platform::open();
        assert!(!library.is_null(), "cannot load {:?}", platform::LIBRARY);
        let find = |name: &CStr| {
            let address = platform::symbol(library, name);
            assert!(
                !address.is_null(),
                "{:?} has no {name:?}",
                platform::LIBRARY
            );
            address
        };
        // SAFETY: each address is the C library's function of that name, which has this signature.
        unsafe {
            Functions {
                cbrt: std::mem::transmute::<*mut c_void, extern "C" fn(f64) -> f64>(find(c"cbrt")),
                pow: std::mem::transmute::<*mut c_void, extern "C" fn(f64, f64) -> f64>(find(
                    c"pow",
                )),
                atan2: std::mem::transmute::<*mut c_void, extern "C" fn(f64, f64) -> f64>(find(
                    c"atan2",
                )),
                cos: std::mem::transmute::<*mut c_void, extern "C" fn(f64) -> f64>(find(c"cos")),
                sin: std::mem::transmute::<*mut c_void, extern "C" fn(f64) -> f64>(find(c"sin")),
            }
        }
    })
}

pub(crate) fn cbrt(x: f64) -> f64 {
    (functions().cbrt)(x)
}

pub(crate) fn pow(x: f64, y: f64) -> f64 {
    (functions().pow)(x, y)
}

pub(crate) fn atan2(y: f64, x: f64) -> f64 {
    (functions().atan2)(y, x)
}

pub(crate) fn cos(x: f64) -> f64 {
    (functions().cos)(x)
}

pub(crate) fn sin(x: f64) -> f64 {
    (functions().sin)(x)
}

/// `math.hypot(x, y)`: CPython's `math_hypot_impl` and `vector_norm` (`Modules/mathmodule.c`),
/// which never call the C library's `hypot`.
pub(crate) fn hypot(x: f64, y: f64) -> f64 {
    let coordinates = [x.abs(), y.abs()];
    let found_nan = coordinates.iter().any(|value| value.is_nan());
    let max = coordinates
        .iter()
        .fold(0.0, |max, &value| if value > max { value } else { max });
    vector_norm(coordinates, max, found_nan)
}

fn vector_norm(coordinates: [f64; 2], max: f64, found_nan: bool) -> f64 {
    if max.is_infinite() {
        return max;
    }
    if found_nan {
        return f64::NAN;
    }
    if max == 0.0 {
        return max;
    }
    let max_e = frexp_exponent(max);
    if max_e < -1023 {
        return f64::MIN_POSITIVE
            * vector_norm(
                coordinates.map(|value| value / f64::MIN_POSITIVE),
                max / f64::MIN_POSITIVE,
                found_nan,
            );
    }
    let scale = two_to(-max_e);
    let (mut csum, mut frac1, mut frac2) = (1.0, 0.0, 0.0);
    for value in coordinates {
        let x = value * scale;
        let (product, product_error) = exact_product(x, x);
        let (sum, sum_error) = fast_sum(csum, product);
        csum = sum;
        frac1 += product_error;
        frac2 += sum_error;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let (product, product_error) = exact_product(-h, h);
    let (sum, sum_error) = fast_sum(csum, product);
    csum = sum;
    frac1 += product_error;
    frac2 += sum_error;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);
    h / scale
}

fn exact_product(x: f64, y: f64) -> (f64, f64) {
    let z = x * y;
    (z, x.mul_add(y, -z))
}

fn fast_sum(a: f64, b: f64) -> (f64, f64) {
    let x = a + b;
    (x, (a - x) + b)
}

/// The exponent C's `frexp` returns for a positive finite number: `value = m * 2^e`, `0.5 <= m < 1`.
fn frexp_exponent(value: f64) -> i32 {
    let biased = ((value.to_bits() >> 52) & 0x7ff) as i32;
    if biased == 0 {
        frexp_exponent(value * two_to(54)) - 54
    } else {
        biased - 1022
    }
}

/// `ldexp(1.0, exponent)` for exponents from -1074 to 1023, exactly.
fn two_to(exponent: i32) -> f64 {
    if exponent >= -1022 {
        f64::from_bits(((exponent + 1023) as u64) << 52)
    } else {
        f64::from_bits(1u64 << (exponent + 1074))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hypot_handles_the_edges_as_cpython_does() {
        assert_eq!(hypot(3.0, 4.0), 5.0);
        assert_eq!(hypot(-0.0, 0.0), 0.0);
        assert_eq!(hypot(f64::INFINITY, f64::NAN), f64::INFINITY);
        assert!(hypot(1.0, f64::NAN).is_nan());
        assert_eq!(hypot(5e-324, 0.0), 5e-324);
        assert_eq!(hypot(3e-310, 4e-310), 5e-310);
    }

    // CPython 3.14 on glibc: `math.cbrt(27.0)` is 3.0000000000000004, where a correctly rounded
    // cube root (Rust's own) gives 3.0.
    #[cfg(target_os = "linux")]
    #[test]
    fn cbrt_is_glibcs() {
        assert_eq!(cbrt(27.0), 3.0000000000000004);
    }

    #[test]
    fn the_c_library_functions_are_found() {
        assert_eq!(cbrt(8.0), 2.0);
        assert_eq!(pow(2.0, 10.0), 1024.0);
        assert_eq!(atan2(0.0, 1.0), 0.0);
        assert_eq!(cos(0.0), 1.0);
        assert_eq!(sin(0.0), 0.0);
    }
}
