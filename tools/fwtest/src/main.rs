//! fwtest: FlexWeek's test harness. The contract is docs/tooling/fwtest.md.

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "fwtest", about = "Run FlexWeek checks one job at a time")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Stop processes left by a finished job and drop its record.
    Clean,
    /// Run ruff, mypy, pytest and the diff whitespace checks.
    Gate {
        /// Skip the desktop import check and run only backend/tests.
        #[arg(long)]
        backend_only: bool,
        /// Pytest workers. Default is half the cores, and at least 2.
        #[arg(long)]
        workers: Option<u32>,
        /// Python interpreter. Overrides FWTEST_PYTHON and .venv/bin/python.
        #[arg(long)]
        python: Option<std::path::PathBuf>,
    },
    /// Break one rule at a time and check that its test goes red.
    Mutate {
        /// Run only the case with this name.
        #[arg(long)]
        case: Option<String>,
        /// Python interpreter. Overrides FWTEST_PYTHON and .venv/bin/python.
        #[arg(long)]
        python: Option<std::path::PathBuf>,
        /// Spec files. Default is every scripts/mutations/*.json in the checkout.
        specs: Vec<std::path::PathBuf>,
    },
    /// Start the hidden session, run the rig driver, then stop that session.
    Rig {
        /// Python interpreter. Overrides FWTEST_PYTHON and .venv/bin/python.
        #[arg(long)]
        python: Option<std::path::PathBuf>,
        /// Arguments forwarded to scripts/rig/drive.py.
        #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
        args: Vec<String>,
    },
    /// Run a command as one contained job.
    Run {
        /// Stop the job after this many seconds (exit 124).
        #[arg(long)]
        timeout: Option<u64>,
        /// Command to run. Put it after `--`.
        #[arg(last = true, required = true, num_args = 1..)]
        command: Vec<String>,
    },
}

fn main() {
    let mut args = std::env::args();
    let _argv0 = args.next();
    if args.next().as_deref() == Some("--inside-rig") {
        let rest: Vec<String> = args.collect();
        std::process::exit(fwtest::rig::inside(&rest));
    }
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Clean => fwtest::clean::run().0,
        Command::Gate {
            backend_only,
            workers,
            python,
        } => fwtest::gate::run(backend_only, workers, python.as_deref()),
        Command::Mutate {
            case,
            python,
            specs,
        } => fwtest::mutate::run(&specs, case.as_deref(), python.as_deref()),
        Command::Rig { python, args } => fwtest::rig::run(&args, python.as_deref()),
        Command::Run { timeout, command } => fwtest::contain::execute(&command, timeout),
    };
    std::process::exit(i32::from(code));
}
