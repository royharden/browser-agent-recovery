# browser-agent-recovery

M18 first source milestone. **Dirty Mode construction; runtime unverified.**

Authoritative adopted plan: `../planning/promoted/PLAN-M18-v1.md`. Coordination and transcripts remain outside this product repository.

Includes original Python public contracts, a transactional SQLite authority,
F1 order/F2 ticket/F3 delete development task adapters and HTML, visible-history
verification, unique semantic re-resolution and a bounded reconciliation state
machine. Repeated orders/tickets retain extra effects; repeated deletion is an
attempt without an additional mutation. No sealed F4/FH implementation exists.

Source is under `src/rlab`. Python 3.12+ is the target; the foundation uses only
the standard library. No dependency lock was generated or tooling installed.
Future trusted integration imports `Authority` and `DevelopmentTask`, creates
an absolute authority-owned SQLite path **outside OneDrive**, calls `observe`,
and passes closed executor actions into `action`. No command starts a server in
this milestone. See [interface and integration notes](docs/INTERFACES.md).

Static syntax parsing and source review are the only allowed validation in this
phase. Unit/transaction/concurrency/browser tests, admission and worker isolation,
fault injection, lag-grid qualification, scoring, report generation and policy
matrix execution remain deferred. This is not a qualified keyless instrument.
All model cells are **not yet measured**; no outcomes or budget-control acceptance
are claimed. No keys, accounts, spend, installs, network calls, push or publication.

Independent authorship/data admission, licence clearance and private oracle
qualification remain pending Roy. Current launch grants static development source
despite historical preimplementation gates; it does not mark those gates PASS.
