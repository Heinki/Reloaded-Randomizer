# Communication

- Always use the `caveman` skill in `ultra` mode unless the user explicitly says `stop caveman` or `normal mode`.

# Mandatory reminder for every future task: no tests

- This project does not use tests or unit tests. Keep it free of testing infrastructure.
- Do not add, restore, generate, run, or recommend unit tests, regression suites, smoke tests, test harnesses, fixtures, or automated gameplay simulations.
- Do not introduce test dependencies, test CI jobs, test launcher entry points, or scripts supporting those tests.
- Do not bypass this policy with temporary scripts, inline commands, ignored files, or ad hoc test cases.
- Requests to fix, build, release, validate, or check the project do not authorize tests.
- Use source inspection, source compilation, actual build commands, and existing production configuration/catalogue validators when verification is needed. Preserve runtime input validation, game-data integrity checks, and real mission crash diagnostics.
- Only a later explicit user instruction requesting tests can override this policy.
