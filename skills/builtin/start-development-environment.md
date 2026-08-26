# start-development-environment

## Purpose
Sets up the standard development environment including IDE, terminal, and local servers.

## Trigger
"start working", "open my dev environment", "start development"

## Risk Profile
GREEN

## Prerequisites
- VS Code installed
- Node.js installed

## Procedure
1. Open VS Code in `C:\Dev\Project`
2. Open Windows Terminal
3. Run `npm run dev` in the terminal

## Verification
- VS Code process is running
- Terminal is visible
- Local server responds on port 3000

## Failure Modes
- Port 3000 already in use
- Directory not found

## Recovery
- If port in use, find PID and ask user if it should be killed.
