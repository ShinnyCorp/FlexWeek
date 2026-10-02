//! One SQLite connection for the app. Python's sqlite3 is not opened on this file.

use std::sync::Mutex;
use std::thread::ThreadId;
use std::time::Duration;

use pyo3::exceptions::{PyIndexError, PyMemoryError, PyOverflowError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyString};
use rusqlite::types::Value;
use rusqlite::{Connection as SqlConn, Error as SqlError, OpenFlags, ffi, params_from_iter};

use crate::guard;

struct Inner {
    conn: Option<SqlConn>,
}

#[pyclass(name = "Connection")]
pub struct PyConn {
    inner: Mutex<Inner>,
    owner: u64,
    thread: ThreadId,
}

#[pyclass(name = "Cursor")]
struct PyCursor {
    columns: Vec<String>,
    rows: Vec<Vec<Value>>,
    index: usize,
    lastrowid: i64,
    write: bool,
    changes: isize,
}

/// A statement can fail in SQLite or while binding a Python value; the second needs the GIL's error.
enum Failure {
    Sql(SqlError),
    Bind(PyErr),
}

impl From<SqlError> for Failure {
    fn from(error: SqlError) -> Self {
        Failure::Sql(error)
    }
}

#[pyclass(name = "Row")]
struct PyRow {
    columns: Vec<String>,
    values: Vec<Value>,
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyConn>()?;
    module.add_class::<PyCursor>()?;
    module.add_class::<PyRow>()?;
    crate::export!(module, open_connection);
    Ok(())
}

#[pyfunction]
fn open_connection(py: Python<'_>, path: &str) -> PyResult<Py<PyConn>> {
    guard(|| {
        let owner = thread_ident(py)?;
        let thread = std::thread::current().id();
        let opened = py.detach(|| open_sql(path));
        let conn = opened.map_err(|error| sqlite_py(py, &error))?;
        Py::new(
            py,
            PyConn {
                inner: Mutex::new(Inner { conn: Some(conn) }),
                owner,
                thread,
            },
        )
    })
}

/// A plain file name, never a URI. The bundled SQLite is built to read "file:" names as URIs whatever
/// the flags say, so such a relative name gets "./" in front, which names the same file.
fn open_sql(path: &str) -> Result<SqlConn, SqlError> {
    let flags = OpenFlags::default() - OpenFlags::SQLITE_OPEN_URI;
    let name = if path.starts_with("file:") {
        format!("./{path}")
    } else {
        path.to_string()
    };
    let conn = SqlConn::open_with_flags(name, flags)?;
    conn.busy_timeout(Duration::from_secs(10))?;
    Ok(conn)
}

#[pymethods]
impl PyConn {
    fn __enter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __exit__(
        &self,
        py: Python<'_>,
        exc_type: Option<&Bound<'_, PyAny>>,
        _exc: Option<&Bound<'_, PyAny>>,
        _tb: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<bool> {
        guard(|| {
            if exc_type.is_some() {
                self.rollback(py)?;
            } else {
                self.commit(py)?;
            }
            Ok(false)
        })
    }

    #[pyo3(signature = (sql, parameters=None))]
    fn execute<'py>(
        &self,
        py: Python<'py>,
        sql: &str,
        parameters: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Py<PyCursor>> {
        let sql = sql.to_string();
        let parameters = parameters.cloned();
        guard(|| {
            self.check(py)?;
            let params = match &parameters {
                Some(value) => binds(value)?,
                None => Vec::new(),
            };
            let outcome = self.with_conn(py, |conn| run_statement(conn, &sql, params))?;
            Py::new(py, outcome)
        })
    }

    #[getter]
    fn in_transaction(&self, py: Python<'_>) -> PyResult<bool> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| Ok(!conn.is_autocommit()))
        })
    }

    fn commit(&self, py: Python<'_>) -> PyResult<()> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                if !conn.is_autocommit() {
                    conn.execute("COMMIT", [])?;
                }
                Ok(())
            })
        })
    }

    fn rollback(&self, py: Python<'_>) -> PyResult<()> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                if !conn.is_autocommit() {
                    conn.execute("ROLLBACK", [])?;
                }
                Ok(())
            })
        })
    }

    fn close(&self, py: Python<'_>) -> PyResult<()> {
        guard(|| {
            self.check(py)?;
            let mut inner = self.inner.lock().expect("connection");
            inner.conn.take();
            Ok(())
        })
    }
}

impl PyConn {
    fn check(&self, py: Python<'_>) -> PyResult<()> {
        let here = thread_ident(py)?;
        if here != self.owner || std::thread::current().id() != self.thread {
            return Err(sqlite_kind(
                py,
                "ProgrammingError",
                format!(
                    "SQLite objects created in a thread can only be used in that same thread. The object was created in thread id {} and this is thread id {here}.",
                    self.owner
                ),
            ));
        }
        let inner = self.inner.lock().expect("connection");
        if inner.conn.is_none() {
            return Err(sqlite_kind(
                py,
                "ProgrammingError",
                "Cannot operate on a closed database.",
            ));
        }
        Ok(())
    }

    fn with_conn<T: Send>(
        &self,
        py: Python<'_>,
        body: impl FnOnce(&mut SqlConn) -> Result<T, Failure> + Send,
    ) -> PyResult<T> {
        let mut inner = self.inner.lock().expect("connection");
        let Some(mut conn) = inner.conn.take() else {
            return Err(sqlite_kind(
                py,
                "ProgrammingError",
                "Cannot operate on a closed database.",
            ));
        };
        let (conn, outcome) = py.detach(move || {
            let outcome = body(&mut conn);
            (conn, outcome)
        });
        inner.conn = Some(conn);
        outcome.map_err(|failure| match failure {
            Failure::Sql(error) => sqlite_py(py, &error),
            Failure::Bind(error) => error,
        })
    }
}

/// CPython's order: compile, begin a transaction for a write, bind, run. A write that does not
/// compile leaves no transaction open; a value that cannot be bound is raised after the BEGIN.
fn run_statement(
    conn: &mut SqlConn,
    sql: &str,
    params: Vec<PyResult<Value>>,
) -> Result<PyCursor, Failure> {
    let write = is_write(sql);
    let mut stmt = conn.prepare(sql)?;
    if write && conn.is_autocommit() {
        conn.execute("BEGIN DEFERRED", [])?;
    }
    let needed = stmt.parameter_count();
    if params.len() != needed {
        return Err(SqlError::InvalidParameterCount(params.len(), needed).into());
    }
    let params = params
        .into_iter()
        .collect::<PyResult<Vec<Value>>>()
        .map_err(Failure::Bind)?;
    let columns: Vec<String> = stmt
        .column_names()
        .iter()
        .map(|name| (*name).to_string())
        .collect();
    let rows = if columns.is_empty() {
        stmt.execute(params_from_iter(params.iter()))?;
        Vec::new()
    } else {
        let mut query = stmt.query(params_from_iter(params.iter()))?;
        let mut rows = Vec::new();
        while let Some(row) = query.next()? {
            let mut values = Vec::with_capacity(columns.len());
            for index in 0..columns.len() {
                values.push(row.get(index)?);
            }
            rows.push(values);
        }
        rows
    };
    Ok(PyCursor {
        columns,
        rows,
        index: 0,
        lastrowid: conn.last_insert_rowid(),
        write,
        changes: conn.changes() as isize,
    })
}

/// CPython's test: after blanks and SQL comments the text starts with one of these words.
/// `WITH ... INSERT` is therefore not a write, and no transaction is begun for it.
fn is_write(sql: &str) -> bool {
    let bytes = sql.as_bytes();
    let mut at = 0;
    while at < bytes.len() {
        match bytes[at] {
            b' ' | b'\t' | b'\r' | b'\n' => at += 1,
            b'-' if bytes.get(at + 1) == Some(&b'-') => {
                match bytes[at..].iter().position(|&b| b == b'\n') {
                    Some(end) => at += end,
                    None => return false,
                }
            }
            b'/' if bytes.get(at + 1) == Some(&b'*') => {
                match bytes[at + 2..].windows(2).position(|pair| pair == b"*/") {
                    Some(end) => at += end + 4,
                    None => return false,
                }
            }
            _ => break,
        }
    }
    let rest = &bytes[at..];
    [&b"insert"[..], b"update", b"delete", b"replace"]
        .iter()
        .any(|word| rest.len() >= word.len() && rest[..word.len()].eq_ignore_ascii_case(word))
}

fn binds(params: &Bound<'_, PyAny>) -> PyResult<Vec<PyResult<Value>>> {
    if params.is_none() {
        return Ok(Vec::new());
    }
    if params.is_instance_of::<PyString>()
        || params.is_instance_of::<PyBytes>()
        || params.is_instance_of::<PyDict>()
    {
        return Err(sqlite_kind(
            params.py(),
            "ProgrammingError",
            "parameters are a sequence",
        ));
    }
    let mut values = Vec::new();
    for item in params.try_iter()? {
        values.push(bind_one(&item?));
    }
    Ok(values)
}

fn bind_one(value: &Bound<'_, PyAny>) -> PyResult<Value> {
    if value.is_none() {
        return Ok(Value::Null);
    }
    if value.is_instance_of::<PyBool>() {
        let flag: bool = value.extract()?;
        return Ok(Value::Integer(i64::from(flag)));
    }
    if value.is_instance_of::<PyInt>() {
        return match value.extract::<i64>() {
            Ok(number) => Ok(Value::Integer(number)),
            Err(_) => Err(PyOverflowError::new_err(
                "Python int too large to convert to SQLite INTEGER",
            )),
        };
    }
    if value.is_instance_of::<PyFloat>() {
        return Ok(Value::Real(value.extract()?));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(Value::Text(value.extract()?));
    }
    if value.is_instance_of::<PyBytes>() {
        return Ok(Value::Blob(value.extract()?));
    }
    Err(sqlite_kind(
        value.py(),
        "ProgrammingError",
        "parameter type is not supported",
    ))
}

#[pymethods]
impl PyCursor {
    #[getter]
    fn lastrowid(&self) -> i64 {
        self.lastrowid
    }

    /// A write that returns rows counts its changes only once the last row has been read.
    #[getter]
    fn rowcount(&self) -> isize {
        if !self.write {
            -1
        } else if self.index < self.rows.len() {
            0
        } else {
            self.changes
        }
    }

    fn fetchone(&mut self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        guard(|| match self.next_row(py)? {
            Some(row) => Ok(row.into_any()),
            None => Ok(py.None()),
        })
    }

    fn fetchall(&mut self, py: Python<'_>) -> PyResult<Vec<Py<PyRow>>> {
        guard(|| {
            let mut rows = Vec::new();
            while let Some(row) = self.next_row(py)? {
                rows.push(row);
            }
            Ok(rows)
        })
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyRow>>> {
        guard(|| self.next_row(py))
    }
}

impl PyCursor {
    fn next_row(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyRow>>> {
        if self.index >= self.rows.len() {
            return Ok(None);
        }
        let values = self.rows[self.index].clone();
        self.index += 1;
        Ok(Some(Py::new(
            py,
            PyRow {
                columns: self.columns.clone(),
                values,
            },
        )?))
    }
}

#[pymethods]
impl PyRow {
    fn keys(&self) -> Vec<String> {
        self.columns.clone()
    }

    fn __iter__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, pyo3::types::PyIterator>> {
        let values = self
            .values
            .iter()
            .map(|value| cell_to_py(py, value))
            .collect::<Vec<_>>();
        let list = pyo3::types::PyList::new(py, values)?;
        list.try_iter()
    }

    fn __getitem__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let index = if let Ok(name) = key.extract::<String>() {
            self.columns
                .iter()
                .position(|column| column == &name)
                .ok_or_else(|| PyIndexError::new_err(format!("No item with that key: {name}")))?
        } else if let Ok(index) = key.extract::<isize>() {
            let resolved = if index < 0 {
                self.values.len() as isize + index
            } else {
                index
            };
            if resolved < 0 || resolved as usize >= self.values.len() {
                return Err(PyIndexError::new_err("No item with that key"));
            }
            resolved as usize
        } else {
            return Err(PyIndexError::new_err("No item with that key"));
        };
        Ok(cell_to_py(py, &self.values[index]))
    }
}

fn cell_to_py(py: Python<'_>, value: &Value) -> Py<PyAny> {
    match value {
        Value::Null => py.None(),
        Value::Integer(number) => number.into_pyobject(py).unwrap().unbind().into_any(),
        Value::Real(number) => number.into_pyobject(py).unwrap().unbind().into_any(),
        Value::Text(text) => text.into_pyobject(py).unwrap().unbind().into_any(),
        Value::Blob(bytes) => PyBytes::new(py, bytes).unbind().into_any(),
    }
}

fn thread_ident(py: Python<'_>) -> PyResult<u64> {
    py.import("threading")?.call_method0("get_ident")?.extract()
}

pub(crate) fn sqlite_py(py: Python<'_>, error: &SqlError) -> PyErr {
    match error {
        SqlError::InvalidParameterCount(got, needed) => sqlite_kind(
            py,
            "ProgrammingError",
            format!(
                "Incorrect number of bindings supplied. The current statement uses {needed}, and there are {got} supplied."
            ),
        ),
        SqlError::SqliteFailure(sqlite, message) => sqlite_code(
            py,
            sqlite.extended_code,
            message.clone().unwrap_or_else(|| error.to_string()),
        ),
        SqlError::SqlInputError {
            error: sqlite, msg, ..
        } => sqlite_code(py, sqlite.extended_code, msg.clone()),
        other => sqlite_kind(py, "DatabaseError", other.to_string()),
    }
}

/// CPython's table from a SQLite result code to an exception class.
fn sqlite_code(py: Python<'_>, code: i32, message: String) -> PyErr {
    let kind = match code & 0xff {
        ffi::SQLITE_NOMEM => return PyMemoryError::new_err(message),
        ffi::SQLITE_CONSTRAINT | ffi::SQLITE_MISMATCH => "IntegrityError",
        ffi::SQLITE_TOOBIG => "DataError",
        ffi::SQLITE_INTERNAL | ffi::SQLITE_NOTFOUND => "InternalError",
        ffi::SQLITE_MISUSE | ffi::SQLITE_RANGE => "InterfaceError",
        ffi::SQLITE_ERROR
        | ffi::SQLITE_PERM
        | ffi::SQLITE_ABORT
        | ffi::SQLITE_BUSY
        | ffi::SQLITE_LOCKED
        | ffi::SQLITE_READONLY
        | ffi::SQLITE_INTERRUPT
        | ffi::SQLITE_IOERR
        | ffi::SQLITE_FULL
        | ffi::SQLITE_CANTOPEN
        | ffi::SQLITE_PROTOCOL
        | ffi::SQLITE_EMPTY
        | ffi::SQLITE_SCHEMA => "OperationalError",
        _ => "DatabaseError",
    };
    sqlite_kind(py, kind, message)
}

fn sqlite_kind(py: Python<'_>, kind: &str, message: impl Into<String>) -> PyErr {
    let message = message.into();
    let Ok(module) = py.import("sqlite3") else {
        return pyo3::exceptions::PyRuntimeError::new_err(message);
    };
    let Ok(class) = module.getattr(kind) else {
        return pyo3::exceptions::PyRuntimeError::new_err(message);
    };
    match class.call1((message.clone(),)) {
        Ok(value) => PyErr::from_value(value),
        Err(error) => error,
    }
}
