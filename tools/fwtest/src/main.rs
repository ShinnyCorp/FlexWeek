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
    /// Run the same checks as scripts/verify.py.
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
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Clean => fwtest::clean::run().0,
        Command::Gate {
            backend_only,
            workers,
            python,
        } => fwtest::gate::run(backend_only, workers, python.as_deref()),
        Command::Run { timeout, command } => fwtest::contain::execute(&command, timeout),
    };
    std::process::exit(i32::from(code));
}
