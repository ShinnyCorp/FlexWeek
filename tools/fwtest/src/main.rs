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
        Command::Run { timeout, command } => fwtest::contain::execute(&command, timeout),
    };
    std::process::exit(i32::from(code));
}
