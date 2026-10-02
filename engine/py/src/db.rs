//! One SQLite connection for the app. Python's sqlite3 is not opened on this file.

use std::panic::{AssertUnwindSafe, catch_unwind, resume_unwind};
use std::path::Path;
use std::sync::Mutex;
use std::thread::ThreadId;

use pyo3::exceptions::{PyIndexError, PyMemoryError, PyOverflowError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyString};
use rusqlite::types::Value;
use rusqlite::{Connection as SqlConn, Error as SqlError, ffi, params_from_iter};

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

/// A statement can fail in SQLite, while binding a Python value, or inside a store helper.
pub(crate) enum Failure {
    Sql(SqlError),
    Bind(PyErr),
    Store(flexweek_store::StoreError),
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
        let opened = py.detach(|| flexweek_store::open_connection(Path::new(path)));
        let conn = opened.map_err(|error| crate::rest::store_py(py, error))?;
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

    fn load_assignment_rows(
        &self,
        py: Python<'_>,
        user_id: i64,
        ids: Vec<String>,
    ) -> PyResult<Vec<(String, String, i64)>> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                flexweek_store::load_assignment_rows(conn, user_id, &ids).map_err(Failure::Store)
            })
        })
    }

    fn assignment_exists(&self, py: Python<'_>, user_id: i64, id: &str) -> PyResult<bool> {
        let id = id.to_string();
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                flexweek_store::assignment_exists(conn, user_id, &id).map_err(Failure::Store)
            })
        })
    }

    fn count_assignments(&self, py: Python<'_>, user_id: i64) -> PyResult<i64> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                flexweek_store::count_assignments(conn, user_id).map_err(Failure::Store)
            })
        })
    }

    fn insert_assignment(
        &self,
        py: Python<'_>,
        user_id: i64,
        id: &str,
        body: &str,
    ) -> PyResult<()> {
        let id = id.to_string();
        let body = body.to_string();
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| {
                flexweek_store::insert_assignment(conn, user_id, &id, &body).map_err(Failure::Store)
            })
        })
    }

    fn save_assignment(
        &self,
        py: Python<'_>,
        user_id: i64,
        id: &str,
        body: &str,
        revision: i64,
        max_count: i64,
    ) -> PyResult<(String, i64)> {
        let id = id.to_string();
        let body = body.to_string();
        guard(|| {
            self.check(py)?;
            let outcome = self.with_conn(py, |conn| {
                flexweek_store::save_assignment(conn, user_id, &id, &body, revision, max_count)
                    .map_err(Failure::Store)
            })?;
            Ok(match outcome {
                flexweek_store::AssignmentSave::Ready(stored) => ("ok".to_string(), stored),
                flexweek_store::AssignmentSave::Conflict => ("conflict".to_string(), 0),
                flexweek_store::AssignmentSave::OverLimit => ("limit".to_string(), 0),
            })
        })
    }

    fn delete_assignment(
        &self,
        py: Python<'_>,
        user_id: i64,
        id: &str,
        revision: &Bound<'_, PyInt>,
    ) -> PyResult<(String, String)> {
        let id = id.to_string();
        let revision = revision_in_range(revision);
        guard(|| {
            self.check(py)?;
            let outcome = self.with_conn(py, |conn| {
                flexweek_store::delete_assignment(conn, user_id, &id, revision)
                    .map_err(Failure::Store)
            })?;
            Ok(match outcome {
                flexweek_store::AssignmentDelete::Missing => ("missing".to_string(), String::new()),
                flexweek_store::AssignmentDelete::Conflict => {
                    ("conflict".to_string(), String::new())
                }
                flexweek_store::AssignmentDelete::Deleted(payload) => ("ok".to_string(), payload),
            })
        })
    }

    fn list_account_weeks(&self, py: Python<'_>, user_id: i64) -> PyResult<Vec<(String, String)>> {
        self.store(py, move |conn| {
            flexweek_store::list_account_weeks(conn, user_id)
        })
    }

    fn save_week(
        &self,
        py: Python<'_>,
        user_id: i64,
        week_start: &str,
        blocks: &str,
        revision: i64,
    ) -> PyResult<(String, i64)> {
        let week_start = week_start.to_string();
        let blocks = blocks.to_string();
        self.store(py, move |conn| {
            flexweek_store::save_week(conn, user_id, &week_start, &blocks, revision)
        })
        .map(|outcome| match outcome {
            flexweek_store::WeekSave::Ready(stored) => ("ok".to_string(), stored),
            flexweek_store::WeekSave::Conflict => ("conflict".to_string(), 0),
        })
    }

    fn capture_account(&self, py: Python<'_>, user_id: i64) -> PyResult<String> {
        self.store(py, move |conn| {
            flexweek_store::capture_account(conn, user_id)
        })
    }

    fn prune_restore_points(
        &self,
        py: Python<'_>,
        user_id: i64,
        keep_ids: Vec<String>,
        keep: i64,
    ) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::prune_restore_points(conn, user_id, &keep_ids, keep)
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn insert_restore_point(
        &self,
        py: Python<'_>,
        user_id: i64,
        point_id: &str,
        label: &str,
        created_at: &str,
        weeks_count: i64,
        assignments_count: i64,
        body: &str,
        keep_ids: Vec<String>,
        keep: i64,
    ) -> PyResult<()> {
        let point_id = point_id.to_string();
        let label = label.to_string();
        let created_at = created_at.to_string();
        let body = body.to_string();
        self.store(py, move |conn| {
            flexweek_store::insert_restore_point(
                conn,
                user_id,
                &point_id,
                &label,
                &created_at,
                weeks_count,
                assignments_count,
                &body,
                &keep_ids,
                keep,
            )
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn adopt_legacy_deadlines(
        &self,
        py: Python<'_>,
        user_id: i64,
        week_start: &str,
        blocks: &str,
        max_assignments: i64,
        encode: Py<PyAny>,
    ) -> PyResult<(bool, String)> {
        let week_start = week_start.to_string();
        let blocks = blocks.to_string();
        guard(|| {
            self.check(py)?;
            let blocks: serde_json::Value = serde_json::from_str(&blocks)
                .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
            let adopted = self.with_conn(py, move |conn| {
                flexweek_store::adopt_legacy_deadlines(
                    conn,
                    user_id,
                    &week_start,
                    &blocks,
                    max_assignments,
                    |body| {
                        Python::attach(|py| {
                            encode
                                .call1(py, (body.to_string(),))
                                .and_then(|text| text.extract::<String>(py))
                        })
                    },
                )
                .map_err(|relay| match relay {
                    flexweek_store::Relay::Store(error) => Failure::Store(error),
                    flexweek_store::Relay::Caller(error) => Failure::Bind(error),
                })
            })?;
            Ok(match adopted {
                flexweek_store::Adopted::OverLimit => (false, "[]".to_string()),
                flexweek_store::Adopted::Blocks(blocks) => {
                    (true, serde_json::Value::Array(blocks).to_string())
                }
            })
        })
    }

    fn require_own_assignments(
        &self,
        py: Python<'_>,
        user_id: i64,
        ids: Vec<String>,
    ) -> PyResult<(bool, Vec<flexweek_store::AssignmentRow>)> {
        self.store(py, move |conn| {
            flexweek_store::own_assignment_rows(conn, user_id, &ids)
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn create_restore_point(
        &self,
        py: Python<'_>,
        user_id: i64,
        token: &str,
        label: &str,
        created_at: &str,
        keep_ids: Vec<String>,
        limit: i64,
    ) -> PyResult<String> {
        let token = token.to_string();
        let label = label.to_string();
        let created_at = created_at.to_string();
        let view = self.store(py, move |conn| {
            flexweek_store::create_restore_point(
                conn,
                user_id,
                &token,
                &label,
                &created_at,
                &keep_ids,
                limit,
            )
        })?;
        Ok(view.to_string())
    }

    fn prune_operations(&self, py: Python<'_>, user_id: i64, keep: i64) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::prune_operations(conn, user_id, keep)
        })
    }

    fn recall_operation(
        &self,
        py: Python<'_>,
        user_id: i64,
        operation_id: &str,
        digest_value: &str,
    ) -> PyResult<(String, String)> {
        let operation_id = operation_id.to_string();
        let digest_value = digest_value.to_string();
        self.store(py, move |conn| {
            flexweek_store::recall_operation(conn, user_id, &operation_id, &digest_value)
        })
        .map(|outcome| match outcome {
            flexweek_store::Recall::Missing => ("missing".to_string(), String::new()),
            flexweek_store::Recall::Conflict => ("conflict".to_string(), String::new()),
            flexweek_store::Recall::Hit(response) => ("ok".to_string(), response),
        })
    }

    fn remember_operation(
        &self,
        py: Python<'_>,
        user_id: i64,
        operation_id: &str,
        digest_value: &str,
        response: &str,
        keep: i64,
    ) -> PyResult<()> {
        let operation_id = operation_id.to_string();
        let digest_value = digest_value.to_string();
        let response = response.to_string();
        self.store(py, move |conn| {
            flexweek_store::remember_operation(
                conn,
                user_id,
                &operation_id,
                &digest_value,
                &response,
                keep,
            )
        })
    }

    fn replace_account(
        &self,
        py: Python<'_>,
        user_id: i64,
        weeks: Vec<(String, String, i64)>,
        assignments: Vec<(String, String, i64)>,
    ) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::replace_account(conn, user_id, &weeks, &assignments)
        })
    }

    fn replace_recovery_codes(
        &self,
        py: Python<'_>,
        user_id: i64,
        hashes: Vec<String>,
    ) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::replace_recovery_codes(conn, user_id, &hashes)
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn save_routine(
        &self,
        py: Python<'_>,
        user_id: i64,
        routine_id: &str,
        name: &str,
        body: &str,
        revision: i64,
        stamp: &str,
        max_count: i64,
    ) -> PyResult<(String, String)> {
        let routine_id = routine_id.to_string();
        let name = name.to_string();
        let body = body.to_string();
        let stamp = stamp.to_string();
        self.store(py, move |conn| {
            flexweek_store::save_routine(
                conn,
                user_id,
                flexweek_store::RoutineWrite {
                    id: &routine_id,
                    name: &name,
                    body: &body,
                    revision,
                    stamp: &stamp,
                    max_count,
                },
            )
        })
        .map(|outcome| match outcome {
            flexweek_store::RoutineSave::Stored(payload) => ("ok".to_string(), payload),
            flexweek_store::RoutineSave::Conflict => ("conflict".to_string(), String::new()),
            flexweek_store::RoutineSave::OverLimit => ("limit".to_string(), String::new()),
        })
    }

    fn delete_routine(
        &self,
        py: Python<'_>,
        user_id: i64,
        routine_id: &str,
        revision: &Bound<'_, PyInt>,
    ) -> PyResult<String> {
        let routine_id = routine_id.to_string();
        let revision = revision_in_range(revision);
        self.store(py, move |conn| {
            flexweek_store::delete_routine(conn, user_id, &routine_id, revision)
        })
        .map(|outcome| match outcome {
            flexweek_store::RoutineDelete::Missing => "missing".to_string(),
            flexweek_store::RoutineDelete::Conflict => "conflict".to_string(),
            flexweek_store::RoutineDelete::Deleted => "ok".to_string(),
        })
    }

    fn list_routines(&self, py: Python<'_>, user_id: i64) -> PyResult<String> {
        self.store(py, move |conn| flexweek_store::list_routines(conn, user_id))
    }

    fn replace_routines(&self, py: Python<'_>, user_id: i64, rows_json: &str) -> PyResult<()> {
        let rows_json = rows_json.to_string();
        self.store(py, move |conn| {
            flexweek_store::replace_routines(conn, user_id, &rows_json)
        })
    }

    fn preference_row(&self, py: Python<'_>, user_id: i64) -> PyResult<Option<String>> {
        self.store(py, move |conn| {
            flexweek_store::preference_row(conn, user_id)
        })
    }

    fn write_preferences(&self, py: Python<'_>, user_id: i64, fields_json: &str) -> PyResult<()> {
        let fields_json = fields_json.to_string();
        self.store(py, move |conn| {
            flexweek_store::write_preferences(conn, user_id, &fields_json)
        })
    }

    fn insert_preferences(&self, py: Python<'_>, user_id: i64, prefs_version: i64) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::insert_preferences(conn, user_id, prefs_version)
        })
    }

    fn delete_account(&self, py: Python<'_>, user_id: i64) -> PyResult<()> {
        self.store(py, move |conn| {
            flexweek_store::delete_account(conn, user_id)
        })
    }

    fn create_session_row(
        &self,
        py: Python<'_>,
        token_hash: &str,
        user_id: i64,
        expires: i64,
        now: i64,
    ) -> PyResult<()> {
        let token_hash = token_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::create_session_row(conn, &token_hash, user_id, expires, now)
        })
    }

    fn begin_immediate(&self, py: Python<'_>) -> PyResult<()> {
        self.store(py, flexweek_store::begin_immediate)
    }

    fn begin(&self, py: Python<'_>) -> PyResult<()> {
        self.store(py, flexweek_store::begin)
    }

    fn enforce_foreign_keys(&self, py: Python<'_>) -> PyResult<()> {
        self.store(py, flexweek_store::enforce_foreign_keys)
    }

    fn session_user(
        &self,
        py: Python<'_>,
        token_hash: &str,
        now: i64,
    ) -> PyResult<Option<(i64, String)>> {
        let token_hash = token_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::session_user(conn, &token_hash, now)
        })
    }

    fn insert_user(&self, py: Python<'_>, username: &str, password_hash: &str) -> PyResult<i64> {
        let username = username.to_string();
        let password_hash = password_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::insert_user(conn, &username, &password_hash)
        })
    }

    fn find_user(&self, py: Python<'_>, username: &str) -> PyResult<Option<(i64, String, String)>> {
        let username = username.to_string();
        self.store(py, move |conn| flexweek_store::find_user(conn, &username))
    }

    fn password_hash_of(&self, py: Python<'_>, user_id: i64) -> PyResult<Option<String>> {
        self.store(py, move |conn| {
            flexweek_store::password_hash_of(conn, user_id)
        })
    }

    fn delete_session(&self, py: Python<'_>, token_hash: &str) -> PyResult<()> {
        let token_hash = token_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::delete_session(conn, &token_hash)
        })
    }

    fn recovery_hashes(&self, py: Python<'_>, user_id: i64) -> PyResult<Vec<String>> {
        self.store(py, move |conn| {
            flexweek_store::recovery_hashes(conn, user_id)
        })
    }

    fn count_recovery_codes(&self, py: Python<'_>, user_id: i64) -> PyResult<i64> {
        self.store(py, move |conn| {
            flexweek_store::count_recovery_codes(conn, user_id)
        })
    }

    fn use_recovery_code(&self, py: Python<'_>, user_id: i64, code_hash: &str) -> PyResult<()> {
        let code_hash = code_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::use_recovery_code(conn, user_id, &code_hash)
        })
    }

    fn rotate_password(&self, py: Python<'_>, user_id: i64, new_hash: &str) -> PyResult<()> {
        let new_hash = new_hash.to_string();
        self.store(py, move |conn| {
            flexweek_store::rotate_password(conn, user_id, &new_hash)
        })
    }

    fn read_week(
        &self,
        py: Python<'_>,
        user_id: i64,
        week_start: &str,
    ) -> PyResult<Option<(String, i64)>> {
        let week_start = week_start.to_string();
        self.store(py, move |conn| {
            flexweek_store::read_week(conn, user_id, &week_start)
        })
    }

    fn week_blocks(
        &self,
        py: Python<'_>,
        user_id: i64,
        week_start: &str,
    ) -> PyResult<Option<String>> {
        let week_start = week_start.to_string();
        self.store(py, move |conn| {
            flexweek_store::week_blocks(conn, user_id, &week_start)
        })
    }

    fn week_starts(&self, py: Python<'_>, user_id: i64) -> PyResult<Vec<String>> {
        self.store(py, move |conn| flexweek_store::week_starts(conn, user_id))
    }

    fn assignment_body(&self, py: Python<'_>, user_id: i64, id: &str) -> PyResult<Option<String>> {
        let id = id.to_string();
        self.store(py, move |conn| {
            flexweek_store::assignment_body(conn, user_id, &id)
        })
    }

    fn assignment_bodies(&self, py: Python<'_>, user_id: i64) -> PyResult<Vec<(String, i64)>> {
        self.store(py, move |conn| {
            flexweek_store::assignment_bodies(conn, user_id)
        })
    }

    fn list_assignment_rows(
        &self,
        py: Python<'_>,
        user_id: i64,
    ) -> PyResult<Vec<(String, String, i64)>> {
        self.store(py, move |conn| {
            flexweek_store::list_assignment_rows(conn, user_id)
        })
    }

    fn list_restore_points(&self, py: Python<'_>, user_id: i64) -> PyResult<String> {
        self.store(py, move |conn| {
            flexweek_store::list_restore_points(conn, user_id)
        })
    }

    fn restore_point_body(
        &self,
        py: Python<'_>,
        user_id: i64,
        point_id: &str,
    ) -> PyResult<Option<(String, String)>> {
        let point_id = point_id.to_string();
        self.store(py, move |conn| {
            flexweek_store::restore_point_body(conn, user_id, &point_id)
        })
    }

    fn availability_json(&self, py: Python<'_>, user_id: i64) -> PyResult<Option<String>> {
        self.store(py, move |conn| {
            flexweek_store::availability_json(conn, user_id)
        })
    }

    fn open_session(&self, py: Python<'_>, token: &str, user_id: i64, now: i64) -> PyResult<()> {
        let token = token.to_string();
        self.store(py, move |conn| {
            flexweek_store::open_session(conn, &token, user_id, now)
        })
    }
}

/// Python compared revisions as unbounded integers; one past `i64` simply matches no row.
fn revision_in_range(revision: &Bound<'_, PyInt>) -> Option<i64> {
    revision.extract::<i64>().ok()
}

impl PyConn {
    pub(crate) fn check(&self, py: Python<'_>) -> PyResult<()> {
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

    pub(crate) fn store<T: Send>(
        &self,
        py: Python<'_>,
        body: impl FnOnce(&rusqlite::Connection) -> flexweek_store::StoreResult<T> + Send,
    ) -> PyResult<T> {
        guard(|| {
            self.check(py)?;
            self.with_conn(py, |conn| body(conn).map_err(Failure::Store))
        })
    }

    pub(crate) fn with_conn<T: Send>(
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
            let outcome = catch_unwind(AssertUnwindSafe(|| body(&mut conn)));
            (conn, outcome)
        });
        inner.conn = Some(conn);
        // Restore the connection and release its lock before the outer guard reports a panic.
        drop(inner);
        let outcome = match outcome {
            Ok(outcome) => outcome,
            Err(payload) => resume_unwind(payload),
        };
        outcome.map_err(|failure| match failure {
            Failure::Sql(error) => sqlite_py(py, &error),
            Failure::Bind(error) => error,
            Failure::Store(error) => crate::rest::store_py(py, error),
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
