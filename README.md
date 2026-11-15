# GAIA — Earth System Trend Detective

GAIA is a planned scientific web application for exploring regional precipitation trends by month, season, and year. It investigates where rainfall is changing, how quickly, and with what statistical evidence, using annual totals to put seasonal changes in context.

**Research question:** In which regions and seasons is surface precipitation changing, at what rate, and with what statistical evidence? How does the picture change when examining annual totals?

## Current status

The repository contains product, architecture, and planning documentation, along with initial configuration files. The project is validating its scope and data. There is no frontend, backend, dataset, or runnable application yet.

Installation, development, build, and run commands are not available at this stage. They will be documented when the corresponding manifests and scripts exist.

## MVP scope

- Two predefined regions, selected after validating data coverage.
- A fixed, versioned monthly precipitation dataset bundled with the application.
- Selection of a time period and aggregation by month, season, or year.
- A regional map, time series, and trend results with units, uncertainty, and provenance.
- Local execution and access without accounts. The installed application must work without an external network connection.
- Read-only SQLite access at runtime, with data preparation performed separately.
- Docker as a future packaging option.

The data source and regions still need validation. A 3D globe, global coverage, file uploads, and user-drawn regions are outside the MVP scope.

## Planned development

The architecture defines a frontend using React Router in Framework Mode with SPA Mode, React, TypeScript, and Vite, and a FastAPI backend that serves the compiled interface and API. Scientific calculations will run in the backend.

The frontend must be initialized with **pnpm** within this project root, without creating an additional enclosing project directory. Once its `package.json` exists, pin an exact, compatible pnpm version in `packageManager`, use pnpm to install dependencies and run scripts, and keep `pnpm-lock.yaml` in Git.

The local `.env` file is excluded from Git. It currently contains only a comment because the application does not read any environment variables yet.

## Documentation

- [Requirements and acceptance criteria](docs/GAIA_requerimientos.md).
- [Architecture, HTTP contracts, and statistical rules](docs/ARCHITECTURE.md).
- [Phases and priorities](docs/ROADMAP.md).
- [Planning conventions](PLANS.md).
- [Working instructions](AGENTS.md).

The requirements and roadmap retain proposals and decisions awaiting validation; the architecture records the MVP's technical decisions. This initial setup prepares the repository for that work.
