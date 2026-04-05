# Infrastructure Immune System

Self-healing autonomous services that monitor and repair the PureTensor fleet.

- **Status:** Active
- **Repo:** github:puretensor/macrophage + gitea:puretensor/immune
- **Runtime:** immune_core on TC (runs as root)
- **Owner:** Heimir Helgason

## Architecture

- Collection of services that autonomously detect and heal issues across the fleet.
- `immune_core` is one component among others (Python service, `python -m immune_core.main`).
- Do not duplicate its functionality when working on infrastructure monitoring.
