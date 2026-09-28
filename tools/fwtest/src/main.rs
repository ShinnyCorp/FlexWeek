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
}

fn main() {
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Clean => fwtest::clean::run(),
    };
    std::process::exit(i32::from(code.0));
}
